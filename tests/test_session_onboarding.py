"""Dedicated-only authentication: prohibited imports never touch a source browser."""
import json

import pytest

from agent_reach.runtime import browser, cdp, cli, state
from agent_reach.runtime.result import ReachError


def test_unmanaged_debugging_port_is_never_closed_or_navigated(monkeypatch):
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(browser, "watcher_running", lambda: False)
    monkeypatch.setattr(browser, "_profile_pids", lambda: [])
    monkeypatch.setattr(cdp, "call", lambda *a, **k: pytest.fail("touched unrelated browser"))
    for operation in (browser.ensure_running, browser.stop, lambda: browser.start("https://example.com")):
        with pytest.raises(ReachError, match="unmanaged"):
            operation()



@pytest.mark.parametrize("args", [
    ["browser", "import", "xiaohongshu", "--opencli-profile", "foreign"],
    ["browser", "profiles"],
    ["ensure", "xiaohongshu", "--reuse-profile", "foreign"],
    ["browser", "import", "xiaohongshu", "--state-file", "private.json"],
])
def test_personal_login_import_is_unavailable(args, monkeypatch, capsys):
    monkeypatch.setattr(browser, "ensure_running", lambda: pytest.fail("opened browser"))
    monkeypatch.setattr(cdp, "call", lambda *a, **k: pytest.fail("read credentials"))
    assert cli.main(args) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "BAD_INPUT"
    assert not state.load().get("reuse_sources")


def test_legacy_cookie_export_and_import_implementations_are_removed():
    from agent_reach.backends import opencli
    assert not hasattr(browser, "import_session")
    assert not hasattr(opencli, "export_site_cookies")
