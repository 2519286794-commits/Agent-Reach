"""Browser lifecycle and DOM boundaries using local fakes, never live accounts."""
import json
import sys
import types

import pytest

from agent_reach.backends import cloak_worker as worker
from agent_reach.runtime.result import ReachError


class BrowserTimeout(Exception):
    pass


@pytest.fixture
def browser_api(monkeypatch):
    monkeypatch.setitem(sys.modules, 'playwright.sync_api', types.SimpleNamespace(
        TimeoutError=BrowserTimeout, Error=RuntimeError))


@pytest.mark.parametrize('channel,names', [
    ('xiaohongshu', ['web_session']), ('boss', ['wt2']),
    ('instagram', ['sessionid', 'ds_user_id']), ('facebook', ['c_user', 'xs']),
    ('twitter', ['auth_token']), ('reddit', ['reddit_session']), ('linkedin', ['li_at']),
])
def test_only_authentication_cookies_confirm_login(channel, names):
    domain = worker.SITES[channel].split('//')[1].removeprefix('www.')
    cookies = [{'name': name, 'value': 'private', 'domain': domain, 'expires': -1} for name in names]
    assert worker.authenticated_cookies(channel, cookies)
    assert not worker.authenticated_cookies(channel, [{**c, 'domain': domain + '.evil.test'} for c in cookies])
    assert not worker.authenticated_cookies(channel, [{**c, 'expires': 1} for c in cookies])
    assert not worker.authenticated_cookies(channel, [{**c, 'value': ''} for c in cookies])
    assert not worker.authenticated_cookies(channel, [{'name': 'webId', 'value': 'visitor', 'domain': domain}])


@pytest.mark.parametrize('close_failure', [False, True])
def test_successful_login_saves_before_close_and_recovers_session_cookies(monkeypatch, tmp_path, browser_api, close_failure):
    binary = tmp_path / 'chrome'
    binary.touch()
    cookies = [{'name': name, 'value': 'private', 'domain': '.instagram.com', 'path': '/', 'expires': -1}
               for name in ('sessionid', 'ds_user_id')]
    events = []
    class Page:
        url = 'about:blank'
        def add_init_script(self, script):
            assert "'role', 'status'" in script
        def goto(self, url, **kwargs):
            self.url = url
        def close(self):
            ctx.pages.remove(self)
        def wait_for_timeout(self, ms):
            events.append('waiting')
    class Context:
        def __init__(self):
            self.pages = [Page()]
        def new_page(self):
            page = Page()
            self.pages.append(page)
            return page
        def cookies(self, urls):
            return cookies
        def close(self):
            assert (tmp_path / 'profile' / 'reach-session.json').is_file()
            events.append('closed')
            if close_failure:
                raise RuntimeError('browser cleanup failed')
    ctx = Context()
    monkeypatch.setattr(worker, 'check_page', lambda page, **kwargs: 'logged in')
    monkeypatch.setattr(worker, 'positive_login_ui', lambda page, channel, text: True)
    monkeypatch.setitem(sys.modules, 'cloakbrowser', types.SimpleNamespace(
        launch_persistent_context=lambda profile, **kwargs: ctx))
    monkeypatch.setitem(sys.modules, 'cloakbrowser.config', types.SimpleNamespace(
        PLATFORM_CHROMIUM_VERSIONS={'local': 'test'}, get_platform_tag=lambda: 'local',
        get_binary_path=lambda _: binary))
    out = worker.execute({'channel': 'instagram', 'action': 'login', 'profile': str(tmp_path / 'profile')})
    assert out[0]['login_detected']
    assert out[0]['window_closed'] is (not close_failure)
    assert events == ['waiting', 'closed']
    snapshot = tmp_path / 'profile' / 'reach-session.json'
    assert len(json.loads(snapshot.read_text())['cookies']) == 2
    restored = []
    worker.restore_session(types.SimpleNamespace(add_cookies=restored.extend, cookies=lambda urls: []),
                           'instagram', tmp_path / 'profile')
    assert [c['name'] for c in restored] == ['sessionid', 'ds_user_id']
    if sys.platform != 'win32':
        assert snapshot.stat().st_mode & 0o777 == 0o600


def test_session_recovery_does_not_overwrite_newer_browser_cookie(tmp_path):
    cookie = {'name': 'web_session', 'domain': '.xiaohongshu.com', 'path': '/', 'value': 'older', 'expires': -1}
    (tmp_path / 'reach-session.json').write_text(json.dumps({'cookies': [cookie]}))
    current = {**cookie, 'value': 'newer'}
    ctx = types.SimpleNamespace(cookies=lambda urls: [current], add_cookies=lambda rows: pytest.fail('must retain current cookie'))
    worker.restore_session(ctx, 'xiaohongshu', tmp_path)


@pytest.mark.parametrize('body', ['', '   ', '加载中...', 'Loading...'])
def test_blank_or_loading_page_is_not_a_login_signal(body):
    page = types.SimpleNamespace(locator=lambda selector: pytest.fail('blank page cannot confirm login'))
    assert worker.positive_login_ui(page, 'xiaohongshu', body) is False


def test_loaded_page_without_self_account_ui_does_not_confirm_login():
    class Links:
        def evaluate_all(self, script, only_me):
            assert only_me is True and "=== '我'" in script
            return False
    assert worker.positive_login_ui(types.SimpleNamespace(locator=lambda selector: Links()),
                                    'xiaohongshu', '首页内容已加载') is False


@pytest.mark.parametrize('failure', ['login', 'query', 'login_wall_after_query'])
def test_failed_action_with_auth_cookie_never_overwrites_verified_snapshot(monkeypatch, tmp_path, browser_api, failure):
    profile = tmp_path / 'profile'
    profile.mkdir()
    cookie = {'name': 'web_session', 'value': 'verified-old', 'domain': '.xiaohongshu.com', 'path': '/', 'expires': -1}
    previous = json.dumps({'cookies': [cookie]})
    snapshot = profile / 'reach-session.json'
    snapshot.write_text(previous)
    binary = tmp_path / 'chrome'
    binary.touch()
    class Page:
        def close(self):
            ctx.pages.remove(self)
    class Context:
        def __init__(self):
            self.pages = [Page()]
        def new_page(self):
            page = Page()
            self.pages.append(page)
            return page
        def cookies(self, urls):
            return [{**cookie, 'value': 'unverified-new'}]
        def close(self):
            pass
    ctx = Context()
    monkeypatch.setitem(sys.modules, 'cloakbrowser', types.SimpleNamespace(
        launch_persistent_context=lambda profile, **kwargs: ctx))
    monkeypatch.setitem(sys.modules, 'cloakbrowser.config', types.SimpleNamespace(
        PLATFORM_CHROMIUM_VERSIONS={'local': 'test'}, get_platform_tag=lambda: 'local', get_binary_path=lambda _: binary))
    def blocked(*args, **kwargs):
        raise ReachError('NEED_LOGIN', 'not authenticated')
    monkeypatch.setattr(worker, 'login', blocked)
    monkeypatch.setattr(worker, 'search', (lambda *args: []) if failure == 'login_wall_after_query' else blocked)
    monkeypatch.setattr(worker, 'check_page', blocked)
    with pytest.raises(ReachError):
        worker.execute({'channel': 'xiaohongshu', 'action': 'login' if failure == 'login' else 'search',
                        'query': 'test', 'profile': str(profile)})
    assert snapshot.read_text() == previous


def test_login_timeout_preserves_existing_snapshot(monkeypatch, tmp_path, browser_api):
    snapshot = tmp_path / 'reach-session.json'
    snapshot.write_text('old session')
    class Page:
        url = 'https://www.xiaohongshu.com'
        def add_init_script(self, script):
            pass
        def goto(self, url, **kwargs):
            pass
        def wait_for_timeout(self, ms):
            pass
    page = Page()
    ctx = types.SimpleNamespace(pages=[page], cookies=lambda urls: [])
    calls = iter([1, 1, 999])
    monkeypatch.setattr(worker.time, 'monotonic', lambda: next(calls))
    page._reach_deadline = 10
    with pytest.raises(ReachError) as caught:
        worker.login(page, ctx, 'xiaohongshu', tmp_path)
    assert caught.value.code == 'TIMEOUT'
    assert snapshot.read_text() == 'old session'


class Locator:
    def __init__(self, text='', count=0):
        self.text, self.total = text, count
    def inner_text(self, **kwargs):
        return self.text
    def count(self):
        return self.total


@pytest.mark.parametrize('body,expected', [
    ('页面加载中', 'TIMEOUT'), ('访问过于频繁', 'RATE_LIMITED'),
    ('请完成验证', 'PLATFORM_BLOCKED'), ('扫码登录', 'NEED_LOGIN'),
    ('笔记不存在', 'NOT_FOUND'),
])
def test_page_timeout_never_guesses_rate_limit(body, expected, browser_api):
    class Page:
        url = 'https://www.xiaohongshu.com/search_result'
        def goto(self, *args, **kwargs):
            return None
        def locator(self, selector):
            return Locator(text=body) if selector == 'body' else Locator()
        def wait_for_selector(self, *args, **kwargs):
            raise BrowserTimeout()
    with pytest.raises(ReachError) as caught:
        worker.navigate(Page(), 'https://www.xiaohongshu.com/search_result', '.note-item', allow_empty=True)
    assert caught.value.code == expected


def test_explicit_empty_search_is_successful_empty_result(browser_api):
    class Page:
        url = 'https://www.xiaohongshu.com/search_result'
        def goto(self, *args, **kwargs):
            return None
        def locator(self, selector):
            return Locator(text='没有找到相关内容') if selector == 'body' else Locator()
        def wait_for_selector(self, *args, **kwargs):
            raise BrowserTimeout()
    assert worker.search(Page(), 'xiaohongshu', {'query': 'no match', 'limit': 1}) == []


def test_comments_returns_threads_and_loaded_replies_without_full_claim(monkeypatch, browser_api):
    class Comments:
        def count(self):
            return 2
        def evaluate_all(self, script, limit):
            assert limit == 1 and 'repliesLeft = 200' in script
            return [{'comment': {'id': 'c1', 'text': 'top', 'author': 'A'},
                     'replies': [{'id': 'c2', 'text': 'reply', 'author': 'B'}]}]
    page = types.SimpleNamespace(wait_for_selector=lambda *a, **kw: None, locator=lambda selector: Comments())
    monkeypatch.setattr(worker, 'navigate', lambda *args, **kwargs: True)
    url = 'https://www.xiaohongshu.com/explore/abc?xsec_token=provided'
    items = worker.comments(page, 'xiaohongshu', {'target': url, 'limit': 1})
    assert [item['text'] for item in items] == ['top', 'reply']
    assert items[1]['raw']['parent_id'] == 'c1'
    assert items[1]['raw']['is_reply']
    assert all(item['raw']['exhaustive'] is False for item in items)
    assert all(item['raw']['replies_scope'] == 'already_loaded' for item in items)


@pytest.mark.parametrize('limit', [True, 0, 51, '2'])
def test_comments_rejects_invalid_limit_before_browser_work(limit):
    with pytest.raises(ReachError) as caught:
        worker.validate_comments('xiaohongshu', {'target': 'https://www.xiaohongshu.com/explore/abc', 'limit': limit})
    assert caught.value.code == 'BAD_INPUT'


class PublicNotePage:
    """A note's own content selectors, with unrelated login controls in the page."""
    url = 'https://www.xiaohongshu.com/explore/public-note'

    def __init__(self, *, body='公开正文 登录/注册', description='这篇笔记的公开正文', missing=False):
        self.body, self.description, self.missing = body, description, missing

    def goto(self, *args, **kwargs):
        return types.SimpleNamespace(status=200)

    def locator(self, selector):
        if selector == 'body':
            return Locator(text=self.body)
        if selector == '#detail-desc':
            return types.SimpleNamespace(all_inner_texts=lambda: [self.description])
        if selector == '#detail-title':
            return Locator(text='公开笔记', count=1)
        return Locator(count=1 if selector == '.login-container:visible' else 0)

    def wait_for_selector(self, selector, **kwargs):
        if self.missing:
            raise BrowserTimeout()


@pytest.mark.parametrize('prompt', ['登录/注册', '扫码登录', '登录查看完整内容', '手机号登录'])
def test_public_note_description_survives_optional_login_prompt(browser_api, prompt):
    page = PublicNotePage(body='公开正文 ' + prompt)
    items = worker.read(page, 'xiaohongshu', page.url)
    assert items[0]['text'] == '这篇笔记的公开正文'
    assert items[0]['raw']['content_scope'] == 'description_only'


@pytest.mark.parametrize('missing', [False, True])
def test_login_prompt_without_requested_description_still_requires_login(browser_api, missing):
    page = PublicNotePage(body='扫码登录', description='', missing=missing)
    with pytest.raises(ReachError) as caught:
        worker.read(page, 'xiaohongshu', page.url)
    assert caught.value.code == 'NEED_LOGIN'


@pytest.mark.parametrize('signal,expected', [
    ('公开正文 访问过于频繁 登录/注册', 'RATE_LIMITED'),
    ('公开正文 请完成验证 登录/注册', 'PLATFORM_BLOCKED'),
])
def test_public_content_never_overrides_platform_safety_signal(browser_api, signal, expected):
    page = PublicNotePage(body=signal)
    with pytest.raises(ReachError) as caught:
        worker.read(page, 'xiaohongshu', page.url)
    assert caught.value.code == expected


def test_search_placeholder_is_not_valid_public_content(monkeypatch, browser_api):
    class SearchPage(PublicNotePage):
        url = 'https://www.xiaohongshu.com/search_result'
        def wait_for_function(self, *args, **kwargs):
            pass
        def locator(self, selector):
            if selector == 'section.note-item':
                return types.SimpleNamespace(count=lambda: 1, evaluate_all=lambda script: [{'title': '', 'url': ''}])
            return super().locator(selector)
    with pytest.raises(ReachError) as caught:
        worker.search(SearchPage(body='扫码登录'), 'xiaohongshu', {'query': 'coffee', 'limit': 1})
    assert caught.value.code == 'NEED_LOGIN'


def test_execute_retains_extracted_public_note_with_login_controls(monkeypatch, tmp_path, browser_api):
    binary = tmp_path / 'chrome'
    binary.touch()
    class Page(PublicNotePage):
        def close(self):
            ctx.pages.remove(self)
    class Context:
        def __init__(self):
            self.pages = [Page()]
        def new_page(self):
            page = Page()
            self.pages.append(page)
            return page
        def cookies(self, urls):
            return []
        def close(self):
            self.closed = True
    ctx = Context()
    monkeypatch.setitem(sys.modules, 'cloakbrowser', types.SimpleNamespace(
        launch_persistent_context=lambda *args, **kwargs: ctx))
    monkeypatch.setitem(sys.modules, 'cloakbrowser.config', types.SimpleNamespace(
        PLATFORM_CHROMIUM_VERSIONS={'local': 'test'}, get_platform_tag=lambda: 'local',
        get_binary_path=lambda _: binary))
    result = worker.execute({'channel': 'xiaohongshu', 'action': 'read',
                             'target': Page.url, 'profile': str(tmp_path / 'profile')})
    assert result[0]['text'] == '这篇笔记的公开正文'
    assert ctx.closed


def test_native_login_autosaves_with_optional_login_text(monkeypatch, tmp_path, browser_api):
    class Page(PublicNotePage):
        def add_init_script(self, script):
            pass
        def wait_for_timeout(self, ms):
            pass
        def locator(self, selector):
            if selector == worker.LOGIN_UI['xiaohongshu']:
                return types.SimpleNamespace(evaluate_all=lambda *args: True)
            return super().locator(selector)
    cookie = {'name': 'web_session', 'value': 'authenticated', 'domain': '.xiaohongshu.com',
              'path': '/', 'expires': -1}
    page = Page(body='我的首页 登录/注册')
    ctx = types.SimpleNamespace(pages=[page], cookies=lambda urls: [cookie])
    result = worker.login(page, ctx, 'xiaohongshu', tmp_path)
    assert result[0]['login_detected']
    assert json.loads((tmp_path / 'reach-session.json').read_text())['cookies'][0]['name'] == 'web_session'
