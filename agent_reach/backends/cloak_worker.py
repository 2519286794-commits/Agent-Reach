"""Private subprocess worker. Only fixed read-only site actions are accepted."""
from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from agent_reach.runtime.result import ReachError, make_item
from agent_reach.utils.url import domain_matches, host_matches

SITES = {"boss": "https://www.zhipin.com", "xiaohongshu": "https://www.xiaohongshu.com",
         "instagram": "https://www.instagram.com", "facebook": "https://www.facebook.com",
         "twitter": "https://x.com", "reddit": "https://www.reddit.com",
         "linkedin": "https://www.linkedin.com"}
CITIES = {"深圳": "101280600", "北京": "101010100", "上海": "101020100", "广州": "101280100",
          "杭州": "101210100", "成都": "101270100", "全国": "100010000"}

# These are authentication cookies, not visitor identifiers such as XHS webId
# or BOSS __zp_stoken__. Their values never leave this private worker.
AUTH_COOKIES = {"xiaohongshu": ({"web_session"},), "boss": ({"wt2"}, {"_wt2"}),
                "instagram": ({"sessionid", "ds_user_id"},), "facebook": ({"c_user", "xs"},),
                "twitter": ({"auth_token"},), "reddit": ({"reddit_session"}, {"token_v2"}),
                "linkedin": ({"li_at"},)}
LOGIN_UI = {
    "xiaohongshu": 'a[href*="/user/profile/"]',
    "boss": '.user-nav .nav-figure img, .nav-figure img',
    "instagram": 'a[href="/direct/inbox/"], a[href="/accounts/edit/"]',
    "twitter": '[data-testid="SideNav_AccountSwitcher_Button"]',
    "facebook": '[aria-label="Your profile"], [aria-label="你的个人主页"], [aria-label="您的个人主页"], a[href="/me/"]',
    "reddit": 'header a[href^="/user/"], #user-dropdown a[href^="/user/"]',
    "linkedin": 'button.global-nav__primary-link-me-menu-trigger, .global-nav__me-photo',
}
EMPTY_SEARCH = ("没有找到相关内容", "未找到相关笔记", "没有搜索到相关笔记", "暂无相关笔记",
                "暂无搜索结果", "No results found", "No results for")


def budget(page, maximum):
    """Keep page waits within the worker's graceful shutdown deadline."""
    remaining = getattr(page, "_reach_deadline", float("inf")) - time.monotonic()
    if remaining <= 0:
        raise ReachError("TIMEOUT", "Page did not finish loading before the deadline",
                         hint="The site did not provide a rate-limit signal. Try again later; do not retry in a loop.")
    return max(1, int(min(maximum, remaining * 1000)))


def authenticated_cookies(channel, cookies):
    domain = (urlsplit(SITES[channel]).hostname or "").removeprefix("www.")
    now = time.time()
    names = {c.get("name") for c in cookies
             if isinstance(c, dict) and domain_matches(c.get("domain", ""), domain)
             and c.get("value") and isinstance(c.get("expires", -1), (int, float))
             and (c.get("expires", -1) == -1 or c.get("expires", -1) > now)}
    return any(group <= names for group in AUTH_COOKIES.get(channel, ()))


def positive_login_ui(page, channel, text):
    if not text.strip() or text.strip() in {"加载中", "加载中...", "Loading", "Loading..."}:
        return False
    # A user menu/inbox/self-profile signal prevents valid-looking stale cookies
    # and an unfinished or blank page from closing the login window early.
    return page.locator(LOGIN_UI[channel]).evaluate_all("""(els, onlyMe) => els.some(el =>
        el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' &&
        (!onlyMe || el.innerText?.trim() === '我'))
    """, channel == "xiaohongshu")


def save_session(ctx, channel, profile):
    """Snapshot only this site's cookies, including session-only cookies."""
    from agent_reach.backends.cloak import scoped_cookies
    from agent_reach.utils.paths import atomic_write_private_text
    cookies = ctx.cookies([SITES[channel]])
    if not authenticated_cookies(channel, cookies):
        return False
    atomic_write_private_text(Path(profile) / "reach-session.json",
                              json.dumps({"cookies": scoped_cookies(channel, cookies)}))
    return True


def restore_session(ctx, channel, profile):
    from agent_reach.backends.cloak import scoped_cookies
    from agent_reach.utils.paths import read_small_text_no_follow
    text = read_small_text_no_follow(Path(profile) / "reach-session.json", max_bytes=2 * 1024 * 1024)
    if text:
        try:
            cookies = scoped_cookies(channel, json.loads(text))
        except (ValueError, ReachError):
            # The Chromium profile remains the primary copy if a snapshot is
            # incomplete. Never delete the user's previous saved profile.
            return
        existing = {(c.get("name"), c.get("domain"), c.get("path")) for c in ctx.cookies([SITES[channel]])}
        missing = [c for c in cookies if (c["name"], c["domain"], c["path"]) not in existing]
        if missing:
            ctx.add_cookies(missing)


def login(page, ctx, channel, profile):
    """Wait for site auth cookies and a page without a login/verification wall."""
    from playwright.sync_api import Error as PlaywrightError
    page.add_init_script("""(() => {
        const show = () => {
            if (!document.body || document.getElementById('reach-login-status')) return;
            const el = document.createElement('div'); el.id = 'reach-login-status';
            el.setAttribute('role', 'status');
            el.textContent = 'Agent Reach：登录成功后自动保存并关闭，无需手动关窗。 Auto-save and close after login.';
            el.style.cssText = 'position:fixed;bottom:12px;right:12px;max-width:280px;padding:10px 14px;background:#173326;color:#fff;font:13px/1.5 system-ui;z-index:2147483647;border-radius:8px;pointer-events:none';
            document.body.appendChild(el);
        };
        document.addEventListener('DOMContentLoaded', show); show();
    })();""")
    try:
        page.goto(SITES[channel], wait_until="domcontentloaded", timeout=budget(page, 30000))
    except PlaywrightError as exc:
        if type(exc).__name__ != "TimeoutError":
            raise
        # Keep the visible login page usable while it is still loading.
    print("登录成功后将自动保存并关闭。 Login saves and closes automatically; no manual close needed.", file=sys.stderr)
    confirmed = False
    while True:
        try:
            pages = list(ctx.pages)
            if not pages:
                raise ReachError("NEED_LOGIN", "Login window was closed before login could be confirmed",
                                 hint="The previous saved session is retained. Run agent-reach cloak login once when ready.")
            valid_page = False
            for current in pages:
                if not host_matches(current.url, urlsplit(SITES[channel]).hostname or ""):
                    continue
                if not authenticated_cookies(channel, ctx.cookies([SITES[channel]])):
                    continue
                try:
                    # Auth cookies plus the account UI below confirm this login;
                    # a public post mentioning login must not prevent auto-save.
                    text = check_page(current, check_login_prompt=False)
                except ReachError as exc:
                    if exc.code in {"NEED_LOGIN", "PLATFORM_BLOCKED", "RATE_LIMITED"}:
                        continue  # The user can finish the visible verification.
                    raise
                if not positive_login_ui(current, channel, text):
                    continue
                valid_page = True
                if confirmed and save_session(ctx, channel, profile):
                    return [{"session_saved": True, "login_detected": True, "identity_verified": False,
                             "verification": "authentication_cookie_and_account_ui", "window_closed": None}]
            confirmed = valid_page
            pages[0].wait_for_timeout(budget(page, 750))
        except PlaywrightError as exc:
            if type(exc).__name__ in {"TargetClosedError", "Error"} and not ctx.pages:
                raise ReachError("NEED_LOGIN", "Login window was closed before login could be confirmed",
                                 hint="The previous saved session is retained. Reopen login once when ready.") from None
            raise


def target_url(channel, target):
    host = urlsplit(SITES[channel]).hostname
    parsed = urlsplit(target)
    if not host_matches(target, host or "") or parsed.scheme != "https" or parsed.port not in (None, 443):
        raise ReachError("BAD_INPUT", "Use a direct HTTPS note/job URL on the selected site")
    pattern = (r"/job_detail/[A-Za-z0-9_-]+\.html" if channel == "boss" else
               r"/jobs/view/\d+/?" if channel == "linkedin" else
               r"/(?:explore|search_result)/[A-Za-z0-9_-]+")
    if not re.fullmatch(pattern, parsed.path):
        raise ReachError("BAD_INPUT", "Expected a direct note/job detail URL")
    return target


def search_url(channel, params):
    query = params.get("query", "")
    if not isinstance(query, str) or not query.strip() or len(query) > 300:
        raise ReachError("BAD_INPUT", "query must contain 1..300 characters")
    if channel == "facebook":
        return SITES[channel] + "/search/top?" + urlencode({"q": query})
    if channel == "twitter":
        return SITES[channel] + "/search?" + urlencode({"q": query, "src": "typed_query", "f": "live"})
    if channel == "reddit":
        return SITES[channel] + "/search/?" + urlencode({"q": query, "type": "posts"})
    if channel == "linkedin":
        return SITES[channel] + "/jobs/search/?" + urlencode({"keywords": query,
                                                                 "location": params.get("location") or ""})
    if channel == "xiaohongshu":
        return SITES[channel] + "/search_result?" + urlencode({"keyword": query, "source": "web_explore_feed"})
    if channel == "instagram":
        return SITES[channel] + "/web/search/topsearch/?" + urlencode({"query": query, "context": "user"})
    city = params.get("city") or "全国"
    code = CITIES.get(city, city)
    if not re.fullmatch(r"\d{9}", code):
        raise ReachError("BAD_INPUT", "Use 深圳/北京/上海/广州/杭州/成都/全国 or a 9-digit BOSS city code")
    return SITES[channel] + "/web/geek/jobs?" + urlencode({"query": query, "city": code})


def check_page(page, *, check_login_prompt=True):
    text = page.locator("body").inner_text(timeout=budget(page, 3000))
    path = urlsplit(page.url).path
    if any(marker in path for marker in ("/checkpoint", "/challenge", "/check/china/add-phone")):
        raise ReachError("PLATFORM_BLOCKED", "Site verification requires human intervention")
    if any(s in text for s in ("访问过于频繁", "请求过于频繁", "操作过于频繁", "Too many requests")):
        raise ReachError("RATE_LIMITED", "Site rate limit; stop and retry later")
    if any(s in text for s in ("安全验证", "访问异常", "滑动验证", "请完成验证", "滑块验证",
                              "Verify you are human", "Confirm you are human", "Access denied")):
        raise ReachError("PLATFORM_BLOCKED", "Site verification requires human intervention")
    if any(marker in path for marker in ("/login", "/authwall", "/i/flow/login")):
        raise ReachError("NEED_LOGIN", "Site login is required")
    # A login button or optional dialog may coexist with public content. During
    # extraction, defer this decision until the requested selector/data is absent.
    # Verification and rate-limit signals above always stop the action.
    if check_login_prompt:
        if any(s in text for s in ("登录/注册", "登录查看完整内容", "扫码登录", "手机号登录")):
            raise ReachError("NEED_LOGIN", "The requested content is unavailable behind a site login prompt")
        if page.locator(".login-container:visible").count():
            raise ReachError("NEED_LOGIN", "Xiaohongshu login dialog blocks the requested content")
    return text


def navigate(page, url, selector, *, allow_empty=False):
    from playwright.sync_api import TimeoutError as BrowserTimeout
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=budget(page, 18000))
    except BrowserTimeout:
        # A slow subresource can time out navigation while cards already exist.
        # Inspect the same page rather than navigating or changing sessions.
        response = None
    if response and response.status == 429:
        raise ReachError("RATE_LIMITED", "Site returned HTTP 429")
    if response and response.status == 401:
        raise ReachError("NEED_LOGIN", "Site returned HTTP 401; login is required")
    if response and response.status == 403:
        raise ReachError("PLATFORM_BLOCKED", "Site denied access (HTTP 403)")
    if response and response.status == 404:
        raise ReachError("UPSTREAM_BROKEN" if allow_empty else "NOT_FOUND", "Site returned HTTP 404")
    if response and response.status >= 500:
        raise ReachError("UPSTREAM_BROKEN", "Site is unavailable (HTTP 5xx)")
    check_page(page, check_login_prompt=False)
    try:
        page.wait_for_selector(selector, timeout=budget(page, 12000))
    except BrowserTimeout:
        text = check_page(page)
        if any(s in text for s in ("笔记不存在", "职位已关闭", "内容不存在")):
            raise ReachError("NOT_FOUND", "Content no longer available") from None
        if allow_empty and any(marker in text for marker in EMPTY_SEARCH):
            return False
        raise ReachError("TIMEOUT", "Expected page content did not appear before the deadline",
                         hint="The page did not finish loading; no rate limit was confirmed. Try later; do not retry in a loop.") from None
    check_page(page, check_login_prompt=False)
    return True


def search(page, channel, params):
    limit = params.get("limit", 5)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ReachError("BAD_INPUT", "limit must be between 1 and 100")
    selector = ({"boss": ".job-card-wrap", "twitter": 'article[data-testid="tweet"]',
                 "reddit": 'a[href*="/comments/"]',
                 "linkedin": 'a[href*="/jobs/view/"]'}).get(channel, "section.note-item")
    if not navigate(page, search_url(channel, params), selector, allow_empty=True):
        return []
    if channel == "xiaohongshu":
        from playwright.sync_api import TimeoutError as BrowserTimeout
        try:
            page.wait_for_function("""selector => [...document.querySelectorAll(selector)].some(e =>
                e.querySelector('.title')?.innerText?.trim() && e.querySelector('a.cover')?.href)
            """, arg=selector, timeout=budget(page, 4000))
        except BrowserTimeout:
            check_page(page)
            raise ReachError("TIMEOUT", "Search cards appeared but their text did not finish loading",
                             hint="The page did not finish loading; no rate limit was confirmed. Try later.") from None
    unchanged = 0
    for _ in range(6):
        count = page.locator(selector).count()
        if count >= limit:
            break
        if getattr(page, "_reach_deadline", float("inf")) - time.monotonic() < 2:
            break
        if not count:
            break
        page.locator(selector).last.scroll_into_view_if_needed(timeout=budget(page, 2000))
        page.mouse.wheel(0, 1400)
        page.wait_for_timeout(budget(page, 1200))
        check_page(page, check_login_prompt=False)
        if page.locator(selector).count() == count:
            unchanged += 1
            if unchanged >= 2:
                break
        else:
            unchanged = 0
    if channel == "twitter":
        rows = page.locator(selector).evaluate_all('''els => els.map(e => ({
            title:e.querySelector('[data-testid="tweetText"]')?.innerText,
            url:e.querySelector('a[href*="/status/"]')?.href
        })).filter(x => x.title && x.url)''')
    elif channel in {"reddit", "linkedin"}:
        rows = page.locator(selector).evaluate_all('''els => els.map(e => ({
            title:e.innerText?.trim(), url:e.href
        })).filter(x => x.title && x.url)''')
    elif channel == "boss":
        rows = page.locator(selector).evaluate_all('''els => els.map(e => ({
            title:e.querySelector('.job-name')?.innerText,
            url:e.querySelector('.job-name')?.href,
            author:e.querySelector('.boss-name')?.innerText,
            salary:e.querySelector('.job-salary')?.innerText,
            location:e.querySelector('.company-location')?.innerText,
            requirements:e.querySelector('.tag-list')?.innerText
        }))''')
    else:
        rows = page.locator(selector).evaluate_all('''els => els.map(e => ({
            title:e.querySelector('.title')?.innerText,
            url:e.querySelector('a.cover')?.href,
            author:e.querySelector('.author .name')?.innerText
        }))''')
    items, seen = [], set()
    for row in rows:
        if not row.get("url") or not row.get("title") or row["url"] in seen:
            continue
        seen.add(row["url"])
        if channel in {"twitter", "reddit", "linkedin"}:
            host = {"twitter": "x.com", "reddit": "reddit.com", "linkedin": "linkedin.com"}[channel]
            if not host_matches(row["url"], host):
                continue
            text = row["title"]
        elif channel == "boss":
            salary = row.get("salary") or ""
            # Never guess dynamically encoded font glyphs as salary digits.
            if any(0xE000 <= ord(c) <= 0xF8FF for c in salary):
                row["salary_encoded"] = True
                row["salary"] = None
            text = " · ".join(row[k] for k in ("salary", "location", "requirements") if row.get(k))
        else:
            text = None
        row["content_scope"] = "search_card"
        items.append(make_item(title=row["title"], url=row["url"], author=row.get("author"), text=text, raw=row))
    if not items:
        check_page(page)
        raise ReachError("UPSTREAM_BROKEN", "Cards loaded but no valid results could be extracted")
    return items[:limit]


def read(page, channel, target):
    url = target_url(channel, target)
    selector = (".job-sec-text" if channel == "boss" else
                "main"
                if channel == "linkedin" else "#detail-desc")
    navigate(page, url, selector)
    if channel == "linkedin":
        from playwright.sync_api import TimeoutError as BrowserTimeout

        try:
            page.wait_for_function("""() => {
                const text = document.querySelector('main')?.innerText || '';
                return text.includes('关于职位') || text.includes('About the job');
            }""", timeout=budget(page, 12000))
        except BrowserTimeout:
            check_page(page)
            raise ReachError("TIMEOUT", "LinkedIn job description did not load before the deadline") from None
    raw: dict = {}
    if channel == "boss":
        title = page.locator(".job-banner h1").inner_text(timeout=budget(page, 3000))
        header = page.locator(".job-banner").inner_text(timeout=budget(page, 3000))
        match = re.search(r"\d+(?:\.\d+)?-\d+(?:\.\d+)?K(?:·\d+薪)?", header)
        raw = {"salary": match.group() if match else None, "content_scope": "job_description"}
    elif channel == "linkedin":
        title = page.title().split(" | ")[0]
        raw = {"content_scope": "job_description"}
    else:
        title = page.locator("#detail-title").inner_text(timeout=budget(page, 3000)) if page.locator("#detail-title").count() else page.title()
        raw = {"content_scope": "description_only", "images_read": False, "video_read": False}
    text = "\n\n".join(page.locator(selector).all_inner_texts())
    if channel == "linkedin":
        marker = next((m for m in ("关于职位", "About the job") if m in text), None)
        if marker is None:
            raise ReachError("UPSTREAM_BROKEN", "LinkedIn job description did not appear")
        text = text.split(marker, 1)[1].split("关于公司", 1)[0].split("About the company", 1)[0][:12000]
    if not text.strip():
        check_page(page)
        raise ReachError("UPSTREAM_BROKEN", "Detail page returned an empty description")
    return [make_item(title=title, url=url, text=text, raw=raw)]


def validate_comments(channel, params):
    if channel != "xiaohongshu":
        raise ReachError("BAD_INPUT", "Cloak comments currently supports Xiaohongshu notes")
    target_url(channel, params.get("target", ""))
    limit = params.get("limit", 20)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise ReachError("BAD_INPUT", "limit must be between 1 and 50 top-level comments")
    return limit


def comments(page, channel, params):
    """Read a bounded set of visible threads and replies already loaded by XHS."""
    from playwright.sync_api import TimeoutError as BrowserTimeout
    limit = validate_comments(channel, params)
    url = params["target"]
    navigate(page, url, "#detail-desc, #noteContainer, .note-detail-mask")
    selector = ".comments-container .parent-comment"
    try:
        page.wait_for_selector(selector, timeout=budget(page, 6000))
    except BrowserTimeout:
        text = check_page(page)
        if any(s in text for s in ("暂无评论", "还没有评论", "共 0 条评论", "共0条评论")):
            return []
        raise ReachError("TIMEOUT", "The note loaded but its comments did not appear before the deadline",
                         hint="No rate limit was confirmed. Comments may still be loading; try later.") from None
    unchanged, stop = 0, "scroll_budget"
    for _ in range(5):
        count = page.locator(selector).count()
        if count >= limit:
            stop = "limit"
            break
        if getattr(page, "_reach_deadline", float("inf")) - time.monotonic() < 2:
            stop = "time_budget"
            break
        # Scroll within the note's own scrolling container, without clicking
        # reply expansion, posting controls, or navigating to another page.
        page.locator(selector).last.evaluate("""el => {
            for (let n = el.parentElement; n; n = n.parentElement) {
                if (n.scrollHeight > n.clientHeight + 20 && /(auto|scroll)/.test(getComputedStyle(n).overflowY)) {
                    n.scrollBy(0, 900); return;
                }
            }
            window.scrollBy(0, 900);
        }""", timeout=budget(page, 2000))
        page.wait_for_timeout(budget(page, 800))
        check_page(page, check_login_prompt=False)
        if page.locator(selector).count() == count:
            unchanged += 1
            if unchanged >= 2:
                stop = "no_more_loaded"
                break
        else:
            unchanged = 0
    threads = page.locator(selector).evaluate_all("""(els, limit) => {
        let repliesLeft = 200;
        const text = (e, s) => e.querySelector(s)?.innerText?.trim() || '';
        const row = e => ({
            id: e.id || e.getAttribute('data-id') || null,
            author: text(e, '.author a.name, .author .name'),
            author_url: e.querySelector('.author a.name')?.href || null,
            text: text(e, '.content .note-text, .content'),
            time: text(e, '.info .date, .date'),
            likes: text(e, '.like-wrapper .count, .like-container .count')
        });
        return els.slice(0, limit).map(e => {
            const top = e.querySelector(':scope > .comment-item') || e.querySelector('.comment-item');
            if (!top) return null;
            const replies = [...e.querySelectorAll('.reply-container .comment-item-sub')].slice(0, repliesLeft);
            repliesLeft -= replies.length;
            return {comment: row(top), replies: replies.map(row)};
        }).filter(Boolean);
    }""", limit)
    items, seen = [], set()
    for index, thread in enumerate(threads):
        top = thread["comment"]
        for is_reply, row in [(False, top), *((True, reply) for reply in thread.get("replies", []))]:
            if not row.get("text"):
                continue
            key = (index, is_reply, row.get("id") or "", row.get("author"), row["text"])
            if key in seen:
                continue
            seen.add(key)
            raw = {**row, "comment_id": row.get("id"), "is_reply": is_reply,
                   "parent_id": top.get("id") if is_reply else None, "thread_index": index,
                   "content_scope": "loaded_comments", "exhaustive": False,
                   "replies_scope": "already_loaded", "top_level_limit": limit,
                   "loaded_top_level": len(threads), "stop_reason": stop}
            items.append(make_item(title=row["text"][:80], url=url, author=row.get("author"),
                                   text=row["text"], raw=raw))
    if not items:
        check_page(page)
        raise ReachError("UPSTREAM_BROKEN", "Comment containers loaded but no comment text could be extracted")
    return items


def execute(request):
    from cloakbrowser import launch_persistent_context
    from cloakbrowser.config import PLATFORM_CHROMIUM_VERSIONS, get_binary_path, get_platform_tag
    channel, action = request["channel"], request["action"]
    allowed = {"search", "profile", "posts", "import", "login"} if channel == "instagram" else {"search", "read", "import", "login"}
    if channel in {"facebook", "twitter", "reddit"}:
        allowed = {"search", "import", "login"}
    if channel == "linkedin":
        allowed = {"jobs", "read", "import", "login"}
    if channel == "xiaohongshu":
        allowed.add("comments")
    if channel not in SITES or action not in allowed:
        raise ReachError("BAD_INPUT", "Unsupported CloakBrowser action")
    if channel == "instagram" and action != "login":
        from agent_reach.backends.instagram_cloak import validate
        validate(action, request)
    # Validate user input before opening a browser.
    if action == "comments":
        validate_comments(channel, request)
    elif action == "read":
        target_url(channel, request["target"])
    elif action in {"search", "jobs"}:
        search_url(channel, request)
        limit = request.get("limit", 5)
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ReachError("BAD_INPUT", "limit must be between 1 and 100")
    # Pin the SDK's platform build. Query execution never downloads/upgrades a binary.
    version = PLATFORM_CHROMIUM_VERSIONS[get_platform_tag()]
    binary = get_binary_path(version)
    if not binary.is_file():
        raise ReachError("NEED_SETUP", "CloakBrowser binary missing; run agent-reach cloak setup")
    os.environ['CLOAKBROWSER_BINARY_PATH'] = str(binary)
    os.environ['CLOAKBROWSER_LICENSE_KEY'] = ''
    deadline = time.monotonic() + max(0.1, request.get("action_timeout", 870 if action == "login" else 25))
    ctx = launch_persistent_context(request["profile"], headless=(action != "login"), browser_version=version,
                                    locale="zh-CN", proxy=os.environ.get("REACH_CLOAK_PROXY") or None)
    login_result = None
    try:
        if action != "import":
            restore_session(ctx, channel, request["profile"])
        # All pages here belong to the Reach-owned profile, never the source Chrome.
        old_pages = list(ctx.pages)
        page = ctx.new_page()
        page._reach_deadline = deadline
        # Keep a tab alive: closing the last headed tab exits Chromium.
        for old in old_pages:
            old.close()
        if action == "login":
            login_result = login(page, ctx, channel, request["profile"])
            return login_result
        if action == "import":
            cookies = json.loads(Path(request["cookie_file"]).read_text())
            from agent_reach.backends.cloak import DOMAINS
            domain = DOMAINS[channel]
            ctx.clear_cookies(domain=re.compile(r"(^|\.)" + re.escape(domain) + r"$"))
            ctx.add_cookies(cookies)
            params = {"query": "数据平台" if channel == "boss" else "VLA", "limit": 1}
            if channel == "facebook":
                from agent_reach.backends.facebook_cloak import search as facebook_search
                facebook_search(page, "OpenAI", 1)
            elif channel == "instagram":
                from agent_reach.backends.instagram_cloak import execute as instagram_execute
                instagram_execute(page, "profile", {"username": "nasa"})
            else:
                if channel == "twitter":
                    params["query"] = "OpenAI"
                elif channel == "reddit":
                    params["query"] = "python"
                elif channel == "linkedin":
                    params["query"] = "data engineer"
                search(page, channel, params)
            # The action-specific extractor completed; optional login controls
            # do not invalidate its verified search/profile content.
            check_page(page, check_login_prompt=False)
            save_session(ctx, channel, request["profile"])
            return [{"access_verified": True, "scope": "search", "identity_verified": False}]
        if channel == "facebook":
            from agent_reach.backends.facebook_cloak import search as facebook_search
            items = facebook_search(page, request["query"], request.get("limit", 5))
        elif channel == "instagram":
            from agent_reach.backends.instagram_cloak import execute as instagram_execute
            items = instagram_execute(page, action, request)
        elif action in {"search", "jobs"}:
            items = search(page, channel, request)
        elif action == "comments":
            items = comments(page, channel, request)
        else:
            items = read(page, channel, request["target"])
        # Each extractor validates its own content (or an explicit empty result).
        check_page(page, check_login_prompt=False)
        save_session(ctx, channel, request["profile"])
        return items
    finally:
        # Failed actions never replace a previously verified snapshot. Confirmed
        # login and successful actions have already saved before this cleanup.
        try:
            ctx.close()
        except Exception:
            if login_result:
                login_result[0]["window_closed"] = False
            else:
                print("Cloak browser cleanup did not complete normally.", file=sys.stderr)
        else:
            if login_result:
                login_result[0]["window_closed"] = True


def main():
    os.umask(0o077)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            items = execute(json.loads(sys.argv[1]))
        result = {"items": items}
    except ReachError as exc:
        result = {"error": {"code": exc.code, "message": exc.message, "hint": exc.hint}}
    except Exception as exc:
        # Browser exceptions may contain signed URLs, page contents or cookies.
        code = "TIMEOUT" if type(exc).__name__ == "TimeoutError" else "UPSTREAM_BROKEN"
        result = {"error": {"code": code, "message": f"CloakBrowser worker failed ({type(exc).__name__})"}}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
