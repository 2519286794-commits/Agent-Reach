# -*- coding: utf-8 -*-
"""OpenCLI backend: run `opencli <site> ...` in the Agent Reach browser.

OpenCLI (github.com/jackwener/opencli) drives Chrome through a browser-bridge
extension + local daemon. Agent Reach uses one shared, Reach-owned browser profile.
"""

import json

OPENCLI_EXTENSION_ID = "ildkmabpimmkaediidaifkhjpohdnifk"
OPENCLI_EXTENSION_URL = (
    f"https://chromewebstore.google.com/detail/opencli/{OPENCLI_EXTENSION_ID}"
)

_NAV_REJECTED_HINT = (
    "OpenCLI's browser extension could not open the page. This is a known open "
    "OpenCLI issue on recent Chrome (github.com/jackwener/opencli/issues/2487); "
    "retrying a few seconds later sometimes works. Do not retry in a loop."
)


def _opencli_error(text: str, login_hint: str):
    """Map OpenCLI's YAML error block (printed even with -f json) to a ReachError."""
    # Node warnings can precede the upstream YAML envelope on stdout. Parse the
    # envelope itself so warnings neither hide error codes nor flood the user.
    import re

    import yaml

    from agent_reach.runtime.result import (
        NEED_LOGIN,
        PLATFORM_BLOCKED,
        RATE_LIMITED,
        UPSTREAM_BROKEN,
        ReachError,
    )
    start = re.search(r"(?m)^ok: false\s*$", text)
    clean = text[start.start():] if start else text
    try:
        doc = yaml.safe_load(clean)
    except yaml.YAMLError:
        doc = None
    err = (doc or {}).get("error") if isinstance(doc, dict) else None
    code = str((err or {}).get("code", "")).upper()
    message = str((err or {}).get("message", "") or text.strip()[:300] or "OpenCLI failed")[:300]
    low = message.lower()
    if any(w in low for w in ("环境异常", "环境存在异常", "browser environment", "captcha", "验证码", "安全验证", "account_risk")) or code in {"ACCOUNT_RISK", "CAPTCHA_REQUIRED"}:
        return ReachError(PLATFORM_BLOCKED, message)
    if code in {"RATE_LIMITED", "RATE_LIMIT"} or any(w in low for w in ("http 429", "too many requests", "访问过于频繁")):
        return ReachError(RATE_LIMITED, message)
    if re.search(r"\bHTTP 404\b", message, re.I) and code not in {"AUTH_REQUIRED", "LOGIN_REQUIRED"}:
        return ReachError(UPSTREAM_BROKEN, message,
                          hint="The upstream route returned HTTP 404. Repeated login will not repair a missing endpoint.")
    login_words = ("login", "log in", "logged in", "sign in", "http 401", "登录")
    if "AUTH" in code or "LOGIN" in code or any(w in low for w in login_words):
        return ReachError(NEED_LOGIN, message, hint=login_hint or None)
    if "navigation rejected" in low:
        return ReachError(UPSTREAM_BROKEN, message, hint=_NAV_REJECTED_HINT)
    return ReachError(UPSTREAM_BROKEN, f"OpenCLI: {message}")


def opencli_call(site: str, args, *, timeout: float, login_hint: str = ""):
    """One bounded command, using an explicit existing browser binding. No retry."""
    from agent_reach.runtime.browser_binding import environment
    from agent_reach.runtime.run import CommandFailed, run_cmd

    env = environment(site)
    argv = ["opencli", site, *args, "-f", "json"]
    try:
        out = run_cmd(argv, timeout=timeout, env=env)
    except CommandFailed as exc:
        raise _opencli_error(exc.stdout or exc.stderr, login_hint) from None
    try:
        data = json.loads(out)
    except ValueError:
        raise _opencli_error(out, login_hint) from None
    if isinstance(data, dict) and data.get("ok") is False:
        raise _opencli_error(out, login_hint)
    from agent_reach.runtime import browser
    browser.save_session()
    return data


def opencli_items(rows) -> list:
    """Map OpenCLI result rows to unified items, keeping each row in `raw`."""
    from agent_reach.runtime.result import make_item, unix_to_iso

    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or [rows]
    items = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue

        def pick(*keys):
            for k in keys:
                v = r.get(k)
                if isinstance(v, dict):
                    v = v.get("nickname") or v.get("name") or v.get("username")
                if v not in (None, ""):
                    return str(v)
            return None

        items.append(
            make_item(
                title=pick("title", "name"),
                url=pick("url", "link", "note_url"),
                author=pick("author", "user", "nickname", "username"),
                published_at=(
                    unix_to_iso(r.get("created_utc"))
                    if isinstance(r.get("created_utc"), (int, float))
                    else pick("published_at", "created_at", "time", "date")
                ),
                text=pick("content", "text", "desc", "description", "body"),
                raw=r,
            )
        )
    return items


def export_site_cookies(profile: str, domain: str) -> list:
    """Read one site's cookies through the official existing Browser Bridge API."""
    from pathlib import Path

    from agent_reach.runtime import bridge
    from agent_reach.runtime.result import NEED_SETUP, ReachError
    from agent_reach.runtime.run import run_cmd
    if not bridge.require_compatible():
        return []
    argv, _ = bridge.launch_spec()
    module = Path(argv[-1]).parent / "browser" / "page.js"
    if not module.is_file():
        raise ReachError(NEED_SETUP, "This OpenCLI version does not expose its Page cookie API")
    script = (f"import {{Page}} from {json.dumps(module.as_uri())};"
              "const page=new Page('reach-site-session',undefined,process.argv[1]);"
              "console.log(JSON.stringify(await page.getCookies({domain:process.argv[2]})));")
    try:
        result = json.loads(run_cmd([argv[0], "--input-type=module", "-e", script, profile, domain], timeout=15))
    except (ReachError, ValueError):
        # Never include upstream output here: it may contain credentials.
        raise ReachError(NEED_SETUP, "The existing browser could not share this site's login") from None
    return result if isinstance(result, list) else []
