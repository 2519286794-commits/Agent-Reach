"""Site-scoped local session reuse. Source browsers are read-only and never cloned.

The user removed the dedicated-only policy. Use existing connected browsers,
then saved Reach state, before requesting a human login. No password/keychain API.
"""
from __future__ import annotations

import json
import time
from contextlib import nullcontext

from agent_reach.utils.paths import PrivatePathError, read_small_text_no_follow

from . import browser, cdp, state
from .browser_binding import execution_lock
from .result import NEED_SETUP, UPSTREAM_BROKEN, ReachError


def _cookies(rows, domains) -> list:
    out = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("name") or "value" not in row:
            continue
        if not any(cdp.domain_matches(str(row.get("domain", "")), domain) for domain in domains):
            continue
        expires = row.get("expires", row.get("expirationDate", -1))
        if not isinstance(expires, (int, float)) or (0 < expires <= time.time()):
            continue
        cookie = {k: row[k] for k in ("name", "value", "domain", "path", "secure", "httpOnly") if k in row}
        cookie["expires"] = expires
        same = {"no_restriction": "None", "lax": "Lax", "strict": "Strict",
                "None": "None", "Lax": "Lax", "Strict": "Strict"}.get(str(row.get("sameSite", "")))
        if same:
            cookie["sameSite"] = same
        out.append(cookie)
    return out


def profiles() -> list:
    return [{"id": context, "dedicated": context == browser.bound_context()}
            for context in browser.connected_contexts()]


def use(profile: str) -> dict:
    if profile == browser.bound_context() or profile not in browser.connected_contexts():
        raise ReachError(NEED_SETUP, "Choose a connected local browser profile from browser profiles")
    state.mutate(lambda data: data.update(local_browser_source=profile, session_reuse={}))
    return {"source_profile": profile, "scope": "requested site only", "source_changed": False}


def _source_cookies(channel: str, domains) -> tuple[list, str]:
    from agent_reach.backends.opencli import export_site_cookies
    contexts = [p["id"] for p in profiles() if not p["dedicated"]]
    preferred = state.load().get("local_browser_source")
    if preferred:
        contexts = [preferred] if preferred in contexts else []
    found = []
    for context in contexts:
        try:
            cookies = _cookies([c for domain in domains for c in export_site_cookies(context, domain)], domains)
        except ReachError:
            continue  # a disconnected source must not prevent use of saved Reach login
        if cookies:
            found.append((cookies, context))
    if len(found) > 1:
        raise ReachError(NEED_SETUP, "Several local browsers have cookies for this site; choose which account to reuse",
                         hint="Run agent-reach browser profiles, then browser use ID. No account was copied.")
    if found:
        return found[0]
    # Older Reach versions stored the user's login in a per-site owned snapshot.
    source = state.root() / "sessions" / (channel + "-cloak") / "profile" / "reach-session.json"
    try:
        data = json.loads(read_small_text_no_follow(source, max_bytes=2 * 1024 * 1024) or "{}")
        cookies = _cookies(data.get("cookies", []), domains)
    except (OSError, ValueError, PrivatePathError):
        cookies = []
    return cookies, "saved-reach-session" if cookies else "saved-profile"


def prepare(channel: str, *, force: bool = False, action_locked: bool = False) -> dict:
    """Try a local login once per hour/site; business success is verified separately."""
    from .manage import _channel, site_domains
    ch = _channel(channel)
    if not ch.login_url:
        return {"source": "not_required", "copied_cookies": 0}
    # Dispatch holds the shared lock in its calling thread while the backend
    # runs in a deadline worker. Never reacquire that OS lock from the worker.
    with nullcontext() if action_locked else execution_lock("browser:shared"):
        browser.ensure_running()
        record = state.load().get("session_reuse", {}).get(channel, {})
        if not force and (record.get("blocked") or record.get("source") == "manual"
                          or (record.get("copied_cookies", 0) > 0 and state.age_seconds(record.get("at")) < 3600)):
            return record
        cookies, source = _source_cookies(channel, site_domains(ch))
        if cookies:
            if cdp.call("Storage.setCookies", {"cookies": cookies}) is None:
                raise ReachError(UPSTREAM_BROKEN, "Could not apply the local site session; the original browser is unchanged")
            browser.save_session()
        result = {"source": source, "copied_cookies": len(cookies), "at": state.now(),
                  "verified": False, "source_changed": False}
        state.mutate(lambda data: data.setdefault("session_reuse", {}).__setitem__(channel, result))
        return result
