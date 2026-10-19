"""The user-facing setup path must reuse sessions and resume without duplicate work."""

import json

import pytest

from agent_reach.mcp_server import _reply
from agent_reach.runtime import flow, manage, state


def test_existing_cloak_session_does_not_import_or_open_login(monkeypatch):
    from agent_reach.backends import cloak

    monkeypatch.setattr(cloak, "status", lambda channel: {"installed": True, "configured": True})
    monkeypatch.setattr(cloak, "import_login", lambda *a, **k: 1 / 0)
    monkeypatch.setattr(flow.manage, "is_added", lambda *a: True)
    monkeypatch.setattr(flow.tools, "present", lambda *a: True)
    result = flow.prepare("xiaohongshu", action="search")
    assert result["status"] == "prepared"
    assert result["backend"] == "cloakbrowser"


def test_explicit_source_grant_is_scoped_and_reused(monkeypatch):
    from agent_reach.backends import cloak
    from agent_reach.runtime import onboarding

    monkeypatch.setattr(cloak, "status", lambda channel: {"configured": False})
    monkeypatch.setattr(cloak, "import_login", lambda channel, **kw: {"imported": 2})
    monkeypatch.setattr(onboarding, "profiles", lambda: {"profiles": [{"id": "chosen"}]})
    monkeypatch.setattr(flow.manage, "is_added", lambda *a: True)
    monkeypatch.setattr(flow.tools, "present", lambda *a: True)
    result = flow.prepare("xiaohongshu", action="search", source_profile="chosen")
    assert result["session_source"] == "authorized_profile"
    assert state.load()["reuse_sources"] == {
        "xiaohongshu": {"profile": "chosen", "granted_at": state.load()["reuse_sources"]["xiaohongshu"]["granted_at"],
                       "scope": "xiaohongshu"}}
    assert flow.forget_source("xiaohongshu")["source_grant_removed"] is True
    assert not state.load().get("reuse_sources", {})


def test_pending_query_resumes_after_login(monkeypatch):
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: flow._needs("xiaohongshu", "search", "login", "Log in"))
    first = flow.execute("xiaohongshu", "search", {"query": "VLA", "limit": 2})
    assert first["status"] == "needs_user_action"
    assert first["operation_id"] in state.load()["pending"]
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: {"ok": True, "status": "prepared"})
    monkeypatch.setattr(flow, "run_action", lambda *a, **k: {
        "ok": True, "backend": "cloakbrowser", "items": [{"title": "VLA", "url": "https://example.test"}],
        "meta": {"attempts": [], "elapsed_ms": 1}, "error": None})
    done = flow.resume(first["operation_id"])
    assert done["status"] == "ready"
    assert first["operation_id"] not in state.load().get("pending", {})


def test_resumed_query_keeps_operation_during_transient_failure(monkeypatch):
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: flow._needs("xiaohongshu", "search", "login", "Log in"))
    first = flow.execute("xiaohongshu", "search", {"query": "VLA", "limit": 2})
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: {"ok": True, "status": "prepared"})
    monkeypatch.setattr(flow, "run_action", lambda *a, **k: {
        "ok": False, "backend": "cloakbrowser", "items": [],
        "meta": {"attempts": [], "elapsed_ms": 1},
        "error": {"code": "UPSTREAM_BROKEN", "message": "Temporary failure"}})
    result = flow.resume(first["operation_id"])
    assert result["status"] == "failed"
    assert result["operation_id"] == first["operation_id"]
    assert first["operation_id"] in state.load()["pending"]


def test_resume_refreshes_only_authorized_source_after_login_failure(monkeypatch):
    saved = state.load()
    saved["pending"] = {"op_test": {"channel": "boss", "action": "search",
                                   "params": {"query": "数据平台"}, "timeout": 60}}
    saved["reuse_sources"] = {"boss": {"profile": "chosen"}}
    state.save(saved)
    calls = []
    def execute_once(*args, **kwargs):
        calls.append("execute")
        return ({"status": "needs_user_action", "required_action": {"type": "login"}}
                if calls.count("execute") == 1 else {"status": "ready", "ok": True})
    def prepare_source(*args, **kwargs):
        assert kwargs["source_profile"] == "chosen"
        calls.append("refresh")
        return {"ok": True}
    monkeypatch.setattr(flow, "execute", execute_once)
    monkeypatch.setattr(flow, "prepare", prepare_source)
    assert flow.resume("op_test")["status"] == "ready"
    assert calls == ["execute", "refresh", "execute"]


def test_mcp_calls_same_flow(monkeypatch):
    monkeypatch.setattr(flow, "ensure", lambda *a, **k: {"ok": True, "status": "ready"})
    reply = _reply({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {
        "name": "reach_ensure", "arguments": {"channel": "boss"}}})
    assert reply["id"] == 7
    assert reply["result"]["structuredContent"]["status"] == "ready"
    assert json.loads(reply["result"]["content"][0]["text"])["ok"] is True


def test_twitter_reddit_search_are_formal_cloak_routes():
    from agent_reach.backends.cloak_worker import search_url

    for channel in ("twitter", "reddit"):
        action = flow._action(flow.manage._channel(channel), "search")
        assert action.backends[0][0] == "cloakbrowser"
        assert "q=python" in search_url(channel, {"query": "python"})


def test_linkedin_jobs_cloak_route_and_url():
    from agent_reach.backends.cloak_worker import search_url

    action = flow._action(flow.manage._channel("linkedin"), "jobs")
    assert [name for name, _ in action.backends] == ["cloakbrowser", "linkedin-mcp"]
    assert "location=Shenzhen" in search_url("linkedin", {"query": "data engineer", "location": "Shenzhen"})


def test_check_fingerprint_ignores_unrelated_tool_changes():
    before = manage.fingerprint("xiaohongshu")
    state.mutate(lambda data: data["tools"].__setitem__("unrelated-cli", {"version": "2"}))
    assert manage.fingerprint("xiaohongshu") == before
    state.mutate(lambda data: data["tools"].__setitem__("cloakbrowser", {"version": "99"}))
    assert manage.fingerprint("xiaohongshu") != before


def test_fresh_jobs_remain_ready_when_old_read_evidence_expires(monkeypatch):
    from agent_reach.backends import cloak

    monkeypatch.setattr(cloak, "status", lambda channel: {"installed": True, "configured": True})
    signature = manage.fingerprint("linkedin")
    def save(data):
        data["channels"]["linkedin"] = {"added_at": state.now()}
        data["checks"]["linkedin"] = {
            "at": state.now(), "scope": "search", "actions": {"jobs": True, "read": True},
            "evidence": {"jobs": {"fingerprint": signature, "at": state.now()},
                         "read": {"fingerprint": signature, "at": "2020-01-01T00:00:00Z"}}}
    state.mutate(save)
    status = manage.channel_status(manage._channel("linkedin"), state.load())
    assert status["status"] == "search_ready"
    assert status["verified_actions"] == ["jobs"]


def test_doctor_shows_recent_import_rate_limit_as_cooldown(monkeypatch):
    from agent_reach.backends import cloak
    from agent_reach.runtime import browser_binding

    monkeypatch.setattr(cloak, "status", lambda channel: {"installed": True, "configured": False})
    monkeypatch.setattr(browser_binding, "profile_for", lambda channel: "chosen")
    monkeypatch.setattr(manage.tools, "present", lambda tool: tool == "opencli")
    def save(data):
        data["channels"]["instagram"] = {"added_at": state.now()}
        data.setdefault("setup_failures", {})["instagram"] = {
            "code": "RATE_LIMITED", "message": "Instagram rate limit", "at": state.now()}
    state.mutate(save)
    status = manage.channel_status(manage._channel("instagram"), state.load())
    assert status["status"] == "cooldown"
    assert status["retry_after_seconds"] > 0
    assert status["problems"] == ["Instagram rate limit"]


def test_query_rate_limit_blocks_repeat_even_with_explicit_source(monkeypatch):
    import datetime

    from agent_reach.backends import cloak

    monkeypatch.setattr(cloak, "status", lambda channel: {"installed": True, "configured": True})
    monkeypatch.setattr(cloak, "import_login", lambda *args, **kwargs: 1 / 0)
    monkeypatch.setattr(flow.manage, "is_added", lambda *args: True)
    monkeypatch.setattr(flow.tools, "present", lambda *args: True)
    flow._record("instagram", "search", {
        "ok": False, "items": [], "backend": None,
        "error": {"code": "RATE_LIMITED", "message": "Instagram API returned HTTP 429"}})
    result = flow.prepare("instagram", action="search", source_profile="chosen")
    assert result["status"] == "cooldown"
    assert result["retry_after_seconds"] > 0
    assert result["error"]["code"] == "RATE_LIMITED"
    assert manage.channel_status(manage._channel("instagram"), state.load())["status"] == "cooldown"
    two_hours_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    def expire(data):
        data["cooldowns"]["instagram"]["at"] = two_hours_ago
        data["checks"]["instagram"]["evidence"]["search"]["at"] = two_hours_ago
    state.mutate(expire)
    assert manage.channel_status(manage._channel("instagram"), state.load())["status"] == "unverified"


@pytest.mark.parametrize("params,timeout", [({}, 60), ({"query": {}}, 60), ({"query": []}, 60),
                                         ({"query": "  \t "}, 60), ({"query": "VLA", "limit": True}, 60),
                                         ({"query": "VLA", "limit": 1.5}, 60), ({"query": "VLA"}, True)])
def test_invalid_execute_does_not_install_or_request_login(monkeypatch, params, timeout):
    from agent_reach.runtime.result import ReachError

    def unexpected(*args, **kwargs):
        raise AssertionError("invalid input cannot start setup")

    monkeypatch.setattr(flow, "prepare", unexpected)
    with pytest.raises(ReachError) as exc:
        flow.execute("xiaohongshu", "search", params, timeout=timeout)
    assert exc.value.code == "BAD_INPUT"


def test_execute_honors_prepared_backend_and_empty_read_is_success(monkeypatch):
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: {"ok": True, "backend": "opencli"})
    seen = {}

    def run(*args, **kwargs):
        seen.update(kwargs)
        return {"ok": True, "items": [], "backend": "opencli", "error": None,
                "meta": {"attempts": [], "elapsed_ms": 1}}

    monkeypatch.setattr(flow, "run_action", run)
    result = flow.execute("xiaohongshu", "read", {"target": "https://www.xiaohongshu.com/explore/test"})
    assert result["ok"] is True and result["items"] == []
    assert seen["preferred_backend"] == "opencli"
    check = state.load()["checks"]["xiaohongshu"]
    assert check["scope"] == "read" and check["codes"] == {}
    assert check["actions"]["read"] is True
    assert check["evidence"]["read"]["verified"] is False
    assert manage.fresh_actions("xiaohongshu", check) == {}


def test_empty_query_keeps_fresh_acceptance_without_extending_it():
    import datetime

    out = {"ok": True, "items": [{"title": "a result"}], "backend": "cloakbrowser", "error": None}
    flow._record("xiaohongshu", "search", out)
    hour_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%SZ")
    state.mutate(lambda data: data["checks"]["xiaohongshu"]["evidence"]["search"].__setitem__("at", hour_ago))
    flow._record("xiaohongshu", "search", {**out, "items": []})
    check = state.load()["checks"]["xiaohongshu"]
    assert check["evidence"]["search"]["at"] == hour_ago
    assert check["last_result"]["item_count"] == 0
    assert manage.fresh_actions("xiaohongshu", check) == {"search": True}
    state.mutate(lambda data: data["checks"]["xiaohongshu"]["evidence"]["search"].__setitem__(
        "at", "2020-01-01T00:00:00Z"))
    flow._record("xiaohongshu", "search", {**out, "items": []})
    assert manage.fresh_actions("xiaohongshu", state.load()["checks"]["xiaohongshu"]) == {}
