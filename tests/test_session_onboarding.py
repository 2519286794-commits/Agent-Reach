"""Reuse contracts: no hidden browser launches, account switches or configuration overwrites."""
import json
from datetime import datetime
from unittest.mock import Mock

import pytest

from agent_reach.channels.boss import BossChannel
from agent_reach.channels.linkedin import LinkedInChannel, _own_config_path
from agent_reach.channels.twitter import TwitterChannel
from agent_reach.config import Config
from agent_reach.runtime import cli, onboarding, state
from agent_reach.runtime.browser_binding import bind_profile, environment, profile_for
from agent_reach.runtime.dispatch import run_action
from agent_reach.runtime.result import ReachError


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('AGENT_REACH_OPENCLI_PROFILE', raising=False)
    monkeypatch.setattr('agent_reach.runtime.tools.resolve', lambda _: '/test/opencli')
    monkeypatch.setattr('agent_reach.runtime.browser.connected_contexts', lambda: ['daily', 'work'])
    monkeypatch.setattr('agent_reach.runtime.browser.start', Mock(side_effect=AssertionError('must not launch')))


def test_one_explicit_choice_reused_without_switching_accounts():
    onboarding.use_profile('daily', '日常 Chrome')
    assert profile_for('twitter') == profile_for('xiaohongshu') == 'daily'
    bind_profile('twitter', 'work')
    assert profile_for('twitter') == 'work'
    assert profile_for('xiaohongshu') == 'daily'
    assert onboarding.profiles()['profiles'][0]['label'] == '日常 Chrome'


def test_discovery_does_not_choose_or_claim_login():
    plan = onboarding.session_plan(TwitterChannel())
    assert plan['profile'] is None
    assert plan['logged_in'] is None
    assert not plan['opened_browser']
    assert len(plan['profiles']) == 2
    assert Config(read_only=True).get('browser_default_profile') is None


def test_disconnected_selection_is_not_replaced(monkeypatch):
    onboarding.use_profile('daily')
    monkeypatch.setattr('agent_reach.runtime.browser.connected_contexts', lambda: ['work'])
    plan = onboarding.session_plan(TwitterChannel())
    assert plan['profile'] == 'daily' and not plan['connected']
    assert environment('twitter')['OPENCLI_PROFILE'] == 'daily'
    with pytest.raises(ReachError):
        onboarding.use_profile('missing')


@pytest.mark.parametrize('endpoint', ['https://example.com:9222', 'http://192.168.1.1:9222',
                                     'http://user:pass@localhost:9222', 'http://localhost:9222/path',
                                     'http://localhost:9222?x=1', 'http://localhost', None])
def test_cdp_binding_rejects_remote_or_ambiguous_addresses(endpoint):
    with pytest.raises(ReachError):
        onboarding.bind_cdp(endpoint)


def test_selected_cdp_and_missing_page_never_launch(monkeypatch):
    onboarding.bind_cdp('http://127.0.0.1:9333')
    assert onboarding.cdp_url() == 'http://127.0.0.1:9333'
    monkeypatch.setattr(onboarding, 'cdp_status', lambda: {'connected': True, 'boss_tab_present': False})
    with pytest.raises(ReachError) as error:
        onboarding.require_boss_cdp()
    assert error.value.code == 'NEED_SETUP'


def test_boss_search_cannot_launch_when_cdp_unavailable(monkeypatch):
    monkeypatch.setattr(onboarding, 'cdp_status', lambda: {'connected': False, 'boss_tab_present': False})
    run = Mock(side_effect=AssertionError('no subprocess without CDP'))
    monkeypatch.setattr('agent_reach.channels.boss.run_cmd', run)
    out = run_action(BossChannel(), 'search', {'query': 'x'})
    assert out['error']['code'] == 'NEED_SETUP'
    run.assert_not_called()


def test_existing_cdp_window_is_not_reopened_even_on_explicit_launch(monkeypatch):
    monkeypatch.setattr(onboarding, 'cdp_status', lambda: {'connected': True, 'boss_tab_present': True})
    popen = Mock(side_effect=AssertionError('already connected'))
    monkeypatch.setattr('subprocess.Popen', popen)
    assert not onboarding.open_boss_browser()['opened_browser']


def test_repeated_linkedin_add_preserves_custom_profile_and_proxy():
    path = _own_config_path()
    path.parent.mkdir(parents=True)
    original = {'mcpServers': {'linkedin': {'command': '/custom/uvx', 'args': ['custom-profile'], 'env': {'HTTPS_PROXY': 'custom'}}}}
    path.write_text(json.dumps(original))
    LinkedInChannel().on_add()
    assert json.loads(path.read_text()) == original


def test_linkedin_reuses_existing_global_registration(monkeypatch):
    monkeypatch.setattr('agent_reach.channels.linkedin.run_cmd', lambda *a, **kw: '{"servers":[{"name":"linkedin"}]}')
    LinkedInChannel().on_add()
    assert not _own_config_path().exists()


def test_login_default_is_read_only_and_modes_are_explicit(capsys):
    assert cli.main(['login', 'twitter']) == 0
    out = json.loads(capsys.readouterr().out)
    assert not out['result']['opened_browser']
    assert cli.main(['login', 'twitter', '--native']) == 1
    assert cli.main(['login', 'boss', '--native', '--new-browser']) == 1


def test_new_default_invalidates_only_inherited_checks():
    bind_profile('twitter', 'work')
    data = state.load()
    data['checks'] = {'twitter': {'actions': {'search': True}}, 'xiaohongshu': {'actions': {'search': True}}, 'github': {'actions': {'search': True}}}
    state.save(data)
    onboarding.use_profile('daily')
    assert 'xiaohongshu' not in state.load()['checks']
    assert 'twitter' in state.load()['checks'] and 'github' in state.load()['checks']


def test_removing_boss_does_not_clear_selected_browser(monkeypatch):
    from agent_reach.runtime import manage
    monkeypatch.setattr(manage, '_channels', lambda: [BossChannel()])
    monkeypatch.setattr(manage, '_prune', lambda data: [])
    clear = Mock(side_effect=AssertionError('must not clear attached browser cookies'))
    monkeypatch.setattr('agent_reach.runtime.browser.clear_site', clear)
    monkeypatch.setattr('agent_reach.runtime.browser.delete_profile', clear)
    data = state.load()
    data['channels']['boss'] = {'added_at': state.now()}
    state.save(data)
    assert manage.remove('boss')['browser_deleted'] is False
    clear.assert_not_called()


def test_native_boss_runner_rejects_wrong_commit_before_browser_import(monkeypatch):
    from agent_reach.backends import boss_native
    class Dist:
        def read_text(self, name):
            return '{"vcs_info":{"commit_id":"unverified"}}'
    monkeypatch.setattr(boss_native, 'distribution', lambda _: Dist())
    monkeypatch.setattr('sys.argv', ['boss_native.py', '{}'])
    assert boss_native.main()['error']['code'] == 'NEED_SETUP'


def test_linkedin_add_does_not_overwrite_malformed_config():
    path = _own_config_path()
    path.parent.mkdir(parents=True)
    path.write_text('{malformed-but-user-owned')
    with pytest.raises(ReachError):
        LinkedInChannel().on_add()
    assert path.read_text() == '{malformed-but-user-owned'


def test_capability_summary_keeps_public_options_separate_from_reach_readiness():
    from agent_reach.runtime.cli import unified_channels

    channels = unified_channels()
    summary = onboarding.capability_summary(
        channels, [{'channel': ch.name, 'status': 'not_added'} for ch in channels])
    entries = {entry['channel']: entry for entry in summary['channels']}
    assert len(entries) == 13
    assert not {'arxiv', 'hackernews', 'xiaoyuzhou', 'xianyu'} & entries.keys()
    for channel in channels:
        entry = entries[channel.name]
        assert entry['reach_status'] == 'not_added'
        assert entry['verified_actions'] == []
        assert [action['action'] for action in entry['actions']] == [a.name for a in channel.actions]
        assert set(entry['authentication']['may_enable_actions']) <= {a.name for a in channel.actions}
        assert entry['authentication']['when'] == 'only_if_required'
    assert 'parent_id' in entries['reddit']['public_access']
    assert set(entries['reddit']['authentication']['may_enable_actions']) == {'search', 'read', 'subreddit'}
    assert '不保证完整评论树' in entries['reddit']['limits'][0]
    assert entries['bilibili']['authentication']['may_enable_actions'] == ['subtitle']
    for name in ('youtube', 'bilibili'):
        assert 'comments' not in [a['action'] for a in entries[name]['actions']]
        assert any('没有独立 comments 动作' in limit for limit in entries[name]['limits'])
    assert entries['youtube']['authentication']['may_enable_actions'] == []


def test_capability_summary_only_labels_evidenced_actions_as_verified():
    from agent_reach.channels.reddit import RedditChannel

    summary = onboarding.capability_summary([RedditChannel()], [{
        'channel': 'reddit', 'status': 'search_ready', 'verified_actions': ['search']}])
    entry = summary['channels'][0]
    assert entry['verified_actions'] == ['search']
    assert entry['reach_status'] == 'search_ready'
    assert '仅搜索已有验收' in summary['message']
    assert '公开搜索' in summary['message']


def test_install_receipt_displays_depth_and_authentication_without_claiming_live_success():
    from agent_reach.runtime.cli import unified_channels

    channels = unified_channels()
    summary = onboarding.capability_summary(channels, [
        {'channel': ch.name, 'status': 'unverified' if ch.level == 'default' else 'not_added'}
        for ch in channels])
    report = onboarding.installation_report({
        'version': 'test', 'capability_summary': summary,
        'default_channels': [{'channel': ch.name, 'ok': True}
                             for ch in channels if ch.level == 'default'],
    })
    assert '5/5 项准备成功' in report
    assert '| 平台 | 不登录可以查什么 | 需要登录后再试 |' in report
    assert report.count('|---|---|---|') == 1
    assert '| Reddit | ✅ 搜帖子、读正文、看评论 | — |' in report
    assert '✅ 不用登录；❌ 登录后再试' in report
    assert '摘要、标题和链接先从搜索引擎找' in report
    assert '试读原文' in report
    assert '❌ 搜笔记、读正文、看评论' in report
    assert '字幕需视频自带' in report
    assert '还没逐项联网测试' in report
    assert '页面提示登录时' not in report
    assert '更多站内功能' not in report
    assert '部分推文' not in report
    assert len(report) <= 700
    for name in ('GitHub', 'YouTube', 'B站', 'V2EX', '网页', 'Reddit', '小红书',
                 'X / Twitter', 'Facebook', 'Instagram', 'LinkedIn', 'BOSS直聘', '雪球'):
        assert '| ' + name + ' |' in report


def test_install_receipt_preserves_failed_installs_and_user_removed_channels():
    from agent_reach.runtime.cli import unified_channels

    channels = unified_channels()
    report = onboarding.installation_report({
        'version': 'test', 'capability_summary': onboarding.capability_summary(channels, []),
        'default_channels': [{'channel': 'web', 'ok': True}, {
            'channel': 'bilibili', 'ok': False, 'error': {'code': 'TIMEOUT'}}],
    })
    assert '1/2 项准备成功' in report
    assert '安装还差一步' in report
    assert '| B站（安装失败：TIMEOUT） |' in report
    assert '| GitHub（保留用户移除） |' in report


@pytest.mark.parametrize(('hour', 'greeting'), [
    (0, '夜深了'), (4, '夜深了'), (5, '早上好呀'), (10, '早上好呀'),
    (11, '中午好'), (13, '中午好'), (14, '下午好'), (17, '下午好'),
    (18, '晚上好'), (21, '晚上好'), (22, '夜深了'), (23, '夜深了'),
])
def test_install_greeting_uses_local_clock_at_period_boundaries(monkeypatch, hour, greeting):
    class LocalClock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is None, 'must use the installing computer local time'
            return cls(2026, 10, 19, hour, 0)

    monkeypatch.setattr(onboarding, 'datetime', LocalClock)
    assert onboarding._local_greeting().startswith(greeting)


def test_install_receipt_does_not_turn_reddit_or_web_failures_into_login(monkeypatch):
    from agent_reach.runtime.cli import unified_channels

    channels = unified_channels()
    monkeypatch.setattr(onboarding, '_local_greeting', lambda: '中午好，想搜点什么？')
    report = onboarding.installation_report({
        'version': 'test', 'capability_summary': onboarding.capability_summary(channels, [
            {'channel': 'reddit', 'status': 'broken'},
            {'channel': 'web', 'status': 'cooldown'},
        ]),
        'default_channels': [{'channel': ch.name, 'ok': True}
                             for ch in channels if ch.level == 'default'],
    })
    rows = [line for line in report.splitlines() if line.startswith(('| Reddit', '| 网页'))]
    assert len(rows) == 2
    assert all('❌' not in row and row.endswith('| — |') for row in rows)
    assert report.startswith('中午好，想搜点什么？\n')
