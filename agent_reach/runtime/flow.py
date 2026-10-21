"""Resumable setup and execution for the CLI.

The caller selects a channel and action. Reach handles its declared primary
backend, reuses available local site sessions, and records a real
query result. No password, cookie, or browser database is exposed here.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from . import manage, state, tools
from .browser_binding import execution_lock
from .dispatch import cooldown, find_action, run_action, validate_action
from .result import BAD_INPUT, NEED_LOGIN, NEED_SETUP, PLATFORM_BLOCKED, RATE_LIMITED, ReachError


def _action(ch, name: Optional[str]):
    action = find_action(ch, name) if name else next(
        (a for a in ch.actions if a.name in ("search", "jobs")), ch.actions[0] if ch.actions else None
    )
    if action is None:
        raise ReachError(BAD_INPUT, f"{ch.name} has no action named {name}")
    return action


def _needs(channel: str, action: str, kind: str, message: str, **extra) -> dict:
    return {"ok": False, "status": "needs_user_action", "channel": channel, "action": action,
            "required_action": {"type": kind, "message": message, **extra}}



def _record(channel: str, action: str, out: dict) -> None:
    stamp = state.now()
    signature = manage.fingerprint(channel)
    def change(data):
        old = data["checks"].get(channel, {})
        actions = dict(old.get("actions", {}))
        actions[action] = bool(out["ok"])
        codes = dict(old.get("codes", {}))
        if actions[action]:
            codes.pop(action, None)
        else:
            codes[action] = (out.get("error") or {}).get("code", "EMPTY")
        evidence = dict(old.get("evidence", {}))
        previous = evidence.get(action, {})
        keep_verified = (out["ok"] and not out["items"] and old.get("actions", {}).get(action)
                         and previous.get("verified", True) and previous.get("item_count", 0) > 0
                         and previous.get("fingerprint") == signature
                         and state.age_seconds(previous.get("at")) < manage.CHECK_FRESH_SECONDS)
        if not keep_verified:
            evidence[action] = {"backend": out.get("backend"), "at": stamp,
                                "item_count": len(out["items"]), "verified": bool(out["ok"] and out["items"]),
                                "fingerprint": signature, "access": out.get("meta", {}).get("access")}
        data["checks"][channel] = {"at": stamp, "actions": actions, "codes": codes,
                                     "previous": old.get("actions", {}), "scope": action,
                                     "evidence": evidence,
                                     "last_result": {"action": action, "at": stamp, "backend": out.get("backend"),
                                                     "item_count": len(out["items"]), "ok": bool(out["ok"]), "error": out.get("error")}}
        if codes.get(action) == RATE_LIMITED:
            data.setdefault("cooldowns", {})[channel] = {
                "code": RATE_LIMITED, "message": (out.get("error") or {}).get("message"), "at": stamp}
        elif actions[action] and state.age_seconds(data.get("cooldowns", {}).get(channel, {}).get("at")) >= 3600:
            data.setdefault("cooldowns", {}).pop(channel, None)
    state.mutate(change)


def prepare(channel: str, *, action: Optional[str] = None,
            install: bool = True) -> dict:
    """Prepare dependencies and the shared browser and reuse the requested site’s local login. No model."""
    ch = manage._channel(channel)
    selected = _action(ch, action)
    with execution_lock("prepare:" + channel):
        limited = cooldown(channel)
        if limited:
            return {"ok": False, "status": "cooldown", "channel": channel,
                    "action": selected.name, "retry_after_seconds": limited["retry_after_seconds"],
                    "error": {"code": RATE_LIMITED, "message": limited["message"]}}
        browser_action = selected.backends[0][0] in {"opencli", "boss-agent-cli"}
        if not browser_action:
            # Native clients prepare their own session only if that route needs it.
            # A stock quote must not provision the whole community browser channel.
            for tool in dict.fromkeys((*ch.prereqs, *ch.tools)):
                if tool in {"chrome", "opencli"} or tools.present(tool):
                    continue
                if not install:
                    return _needs(channel, selected.name, "install", f"Run agent-reach add {channel}")
                tools.ensure(tool)
        elif not manage.is_added(ch) or any(not tools.present(t) for t in manage.channel_tools(ch)):
            if not install:
                return _needs(channel, selected.name, "install", f"Run agent-reach add {channel}")
            manage.add(channel)
        if ch.login_url and browser_action:
            from . import session_reuse
            session_reuse.prepare(channel)
    return {"ok": True, "status": "prepared", "channel": channel,
            "action": selected.name, "backend": selected.backends[0][0]}


def ensure(channel: str, *, action: Optional[str] = None,
           verify: bool = True, install: bool = True) -> dict:
    prepared = prepare(channel, action=action, install=install)
    if not prepared["ok"] or not verify:
        return prepared
    selected = _action(manage._channel(channel), prepared["action"])
    if selected.live_test is None:
        return {**prepared, "status": "prepared", "verified": False}
    out = run_action(manage._channel(channel), selected.name, dict(selected.live_test),
                     timeout=selected.timeout or 60, preferred_backend=prepared.get("backend"), public_first=False)
    _record(channel, selected.name, out)
    if out["ok"]:
        return {**prepared, "status": "ready" if out["items"] else "prepared", "verified": bool(out["items"]),
                "backend": out["backend"], "item_count": len(out["items"])}
    return _failure(channel, selected.name, out)


def _failure(channel: str, action: str, out: dict) -> dict:
    err = out.get("error") or {"code": "EMPTY", "message": "Query returned no items"}
    code = err["code"]
    if code in {NEED_LOGIN, PLATFORM_BLOCKED}:
        return {**_needs(channel, action, "platform_verification" if code == PLATFORM_BLOCKED else "login",
                         err["message"]), "error": err}
    return {"ok": False, "status": "cooldown" if code == RATE_LIMITED else "failed",
            "channel": channel, "action": action, "error": err, "attempts": out["meta"]["attempts"],
            **({"retry_after_seconds": 3600} if code == RATE_LIMITED else {})}


def execute(channel: str, action: str, params: dict[str, Any], *, timeout: float = 60,
            operation_id: Optional[str] = None, backend: Optional[str] = None) -> dict:
    if not isinstance(params, dict):
        raise ReachError(BAD_INPUT, "params must be an object")
    ch = manage._channel(channel)
    _, params = validate_action(ch, action, params, timeout=timeout)
    prepared: dict = {}
    def prepare_site():
        prepared.update(prepare(channel, action=action))
        if not prepared["ok"]:
            err = prepared.get("error")
            if err:
                raise ReachError(err["code"], err["message"], err.get("hint"))
            required = prepared.get("required_action") or {}
            code = {"login": NEED_LOGIN, "platform_verification": PLATFORM_BLOCKED}.get(required.get("type") or "", NEED_SETUP)
            raise ReachError(code, required.get("message") or "Site tool preparation did not complete")

    # Resuming a confirmed auth wall verifies the site path, not another index hit.
    out = run_action(ch, action, params, timeout=timeout, before_backends=prepare_site,
                     public_first=operation_id is None, only_backend=backend)
    if prepared and not prepared["ok"]:
        result = prepared
    else:
        _record(channel, action, out)
        result = ({"ok": True, "status": "ready", "channel": channel, "action": action,
                   "backend": out["backend"], "items": out["items"], "meta": out["meta"]}
                  if out["ok"] else _failure(channel, action, out))
    if result["status"] == "needs_user_action":
        token = operation_id or "op_" + secrets.token_urlsafe(12)
        with execution_lock("pending:" + channel):
            def save_pending(data):
                pending = data.setdefault("pending", {})
                pending[token] = {"channel": channel, "action": action,
                                  "params": params, "timeout": timeout, "backend": backend, "at": state.now()}
                for old in list(pending):
                    if state.age_seconds(pending[old].get("at", "")) > 7 * 86400:
                        pending.pop(old, None)
                while len(pending) > 32:
                    pending.pop(next(iter(pending)))
            state.mutate(save_pending)
        result["operation_id"] = token
    elif operation_id and result["status"] == "ready":
        with execution_lock("pending:" + channel):
            state.mutate(lambda data: data.setdefault("pending", {}).pop(operation_id, None))
    elif operation_id:
        result["operation_id"] = operation_id
    return result


def resume(operation_id: str) -> dict:
    pending = state.load().get("pending", {}).get(operation_id)
    if not pending:
        raise ReachError(BAD_INPUT, "Unknown or completed operation_id")
    result = execute(pending["channel"], pending["action"], pending["params"],
                     timeout=pending["timeout"], operation_id=operation_id, backend=pending.get("backend"))
    return result
