# -*- coding: utf-8 -*-
"""Dedicated tests for Reddit's read-only multi-backend health check."""

from unittest.mock import Mock

import pytest

from agent_reach.channels.reddit import RedditChannel


def test_can_handle_matches_reddit_hosts():
    channel = RedditChannel()
    for url in [
        "https://reddit.com/r/python",
        "https://www.reddit.com/r/python/comments/abc/title/",
        "https://old.reddit.com/r/python",
        "https://redd.it/abc123",
        "HTTPS://REDDIT.COM/r/Python",
    ]:
        assert channel.can_handle(url) is True, url


def test_can_handle_rejects_non_reddit():
    channel = RedditChannel()
    for url in ["https://example.com/r/python", "https://twitter.com/u", ""]:
        assert channel.can_handle(url) is False, url


def test_unconfigured_browser_is_not_a_login_requirement(monkeypatch):
    from agent_reach.backends import cloak
    from agent_reach.runtime import flow
    monkeypatch.setattr(flow.manage, "is_added", lambda *a: True)
    monkeypatch.setattr(flow.tools, "present", lambda *a: True)
    monkeypatch.setattr(flow, "_opencli_ready", lambda *a: False)
    monkeypatch.setattr(cloak, "status", lambda *a: {"configured": False})
    result = flow.prepare("reddit", action="search")
    assert result["status"] == "needs_user_action"
    assert result["required_action"]["type"] == "connect_browser"
    assert "public_search" in result["required_action"]
    assert "public_read" in result["required_action"]


def test_actual_login_error_remains_resumable(monkeypatch):
    from agent_reach.channels import reddit
    from agent_reach.runtime import flow, state
    from agent_reach.runtime.result import NEED_LOGIN, ReachError
    monkeypatch.setattr(flow, "prepare", lambda *a, **k: {"ok": True, "backend": "opencli"})
    request = Mock(side_effect=ReachError(NEED_LOGIN, "Login wall on the selected browser path"))
    monkeypatch.setattr(reddit, "opencli_call", request)
    result = flow.execute("reddit", "search", {"query": "DeepSeek"})
    assert request.call_count == 1
    assert result["required_action"]["type"] == "login"
    assert state.load()["pending"][result["operation_id"]]["params"]["query"] == "DeepSeek"


def test_bare_403_is_not_classified_as_login():
    from agent_reach.backends.opencli import _opencli_error
    assert _opencli_error("HTTP 403 Forbidden", "").code != "NEED_LOGIN"


@pytest.mark.parametrize("backend,expected", [(None, "web"), ("jina", "web"), ("opencli", "reddit")])
def test_read_url_defaults_to_public_web_and_preserves_explicit_browser(monkeypatch, capsys, backend, expected):
    import json

    from agent_reach.runtime import cli
    def run(ch, action, params, **kwargs):
        return {"ok": True, "channel": ch.name, "items": [], "error": None}
    monkeypatch.setattr(cli, "run_action", run)
    argv = ["read", "https://www.reddit.com/r/DeepSeek/comments/test/"]
    if backend:
        argv += ["--backend", backend]
    assert cli.main(argv) == 0
    assert json.loads(capsys.readouterr().out)["channel"] == expected
















def _opencli(installed=True, broken=False, ready=True, hint=""):
    return Mock(installed=installed, broken=broken, ready=ready, hint=hint)
















