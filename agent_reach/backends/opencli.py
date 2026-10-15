# -*- coding: utf-8 -*-
"""OpenCLI backend: run `opencli <site> ...` in the Agent Reach browser.

OpenCLI (github.com/jackwener/opencli) drives Chrome through a browser-bridge
extension + local daemon. Agent Reach binds it to its own dedicated browser
profile (see agent_reach.runtime.browser) and never touches the user's Chrome.
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
    import yaml

    from agent_reach.runtime.result import NEED_LOGIN, UPSTREAM_BROKEN, ReachError

    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        doc = None
    err = (doc or {}).get("error") if isinstance(doc, dict) else None
    code = str((err or {}).get("code", "")).upper()
    message = str((err or {}).get("message", "") or text.strip()[:300] or "OpenCLI failed")[:300]
    low = message.lower()
    login_words = ("login", "log in", "logged in", "sign in", "http 401", "登录")
    if "AUTH" in code or "LOGIN" in code or any(w in low for w in login_words):
        return ReachError(NEED_LOGIN, message, hint=login_hint or None)
    if "navigation rejected" in low:
        return ReachError(UPSTREAM_BROKEN, message, hint=_NAV_REJECTED_HINT)
    return ReachError(UPSTREAM_BROKEN, f"OpenCLI: {message}")


def _dedicated_profile_env() -> dict:
    """OPENCLI_PROFILE for the Agent Reach browser, opening the browser if it is closed.

    Sets the browser up first when it never was (automatic on macOS/Linux; the
    Windows Web Store flow raises NEED_SETUP if the user has not added the extension).
    """
    from agent_reach.runtime import browser

    ctx = browser.bound_context()
    if not ctx:
        browser.setup()
        ctx = browser.bound_context()
    browser.ensure_running(ctx)
    return {"OPENCLI_PROFILE": ctx}


def opencli_call(site: str, args, *, timeout: float, login_hint: str = ""):
    """Run `opencli <site> <args> -f json` in the Agent Reach browser and return parsed JSON."""
    from agent_reach.runtime.run import CommandFailed, run_cmd

    env = _dedicated_profile_env()
    try:
        out = run_cmd(["opencli", site, *args, "-f", "json"], timeout=timeout, env=env)
    except CommandFailed as exc:
        raise _opencli_error(exc.stdout or exc.stderr, login_hint) from None
    try:
        data = json.loads(out)
    except ValueError:
        raise _opencli_error(out, login_hint) from None
    if isinstance(data, dict) and data.get("ok") is False:
        raise _opencli_error(out, login_hint)
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
