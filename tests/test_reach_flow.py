"""Deterministic CLI preparation/execution survives removal of the MCP adapter."""
from unittest.mock import Mock

import pytest

from agent_reach.runtime import flow, state
from agent_reach.runtime.result import ReachError, envelope


def test_execute_prepares_and_runs_the_actual_query_once(monkeypatch):
    prepare = Mock(return_value={"ok": True, "backend": "opencli"})
    run = Mock(return_value=envelope(channel="xiaohongshu", action="search", backend="opencli", items=[{"title": "note"}]))
    monkeypatch.setattr(flow, "prepare", prepare)
    monkeypatch.setattr(flow, "run_action", run)
    out = flow.execute("xiaohongshu", "search", {"query": "VLA"})
    assert out["ok"] and run.call_count == prepare.call_count == 1
    assert state.load()["checks"]["xiaohongshu"]["evidence"]["search"]["item_count"] == 1


def test_pending_query_resumes_without_a_model_or_running_service(monkeypatch):
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: flow._needs("xiaohongshu", "search", "login", "Log in yourself"))
    waiting = flow.execute("xiaohongshu", "search", {"query": "VLA"})
    token = waiting["operation_id"]
    assert state.load()["pending"][token]["params"]["query"] == "VLA"
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: {"ok": True, "backend": "opencli"})
    monkeypatch.setattr(flow, "run_action", lambda *a, **k: envelope(channel="xiaohongshu", action="search", backend="opencli", items=[{"title": "note"}]))
    assert flow.resume(token)["ok"]
    assert token not in state.load()["pending"]


@pytest.mark.parametrize("params", [{}, {"query": "VLA", "unknown": "x"}, {"query": "VLA", "limit": -1}])
def test_invalid_execute_cannot_install_or_open_browser(monkeypatch, params):
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: pytest.fail("invalid request triggered setup"))
    with pytest.raises(ReachError):
        flow.execute("xiaohongshu", "search", params)


def test_unknown_resume_is_explicit_bad_input():
    with pytest.raises(ReachError, match="Unknown"):
        flow.resume("missing")


def test_prepare_reuses_only_the_shared_dedicated_browser(monkeypatch):
    from agent_reach.runtime import browser, manage, tools
    monkeypatch.setattr(manage, "is_added", lambda *a: True)
    monkeypatch.setattr(tools, "present", lambda *a: True)
    ready = Mock()
    monkeypatch.setattr(browser, "ensure_running", ready)
    assert not hasattr(browser, "import_session")
    flow.prepare("xiaohongshu")
    assert ready.call_count == 1
    assert not state.load().get("reuse_sources"), "no indefinite export authorization"


@pytest.mark.parametrize("argv", [["ask","find VLA"],["mcp"],["cloak","setup"],["browser","repair-opencli"]])
def test_retired_commands_are_rejected_without_starting_any_service(argv, monkeypatch, capsys):
    from agent_reach.runtime import browser, cli
    monkeypatch.setattr(browser,"ensure_running",lambda *a,**k:pytest.fail("retired command started browser"))
    assert cli.main(argv) == 1
    import json
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BAD_INPUT"
