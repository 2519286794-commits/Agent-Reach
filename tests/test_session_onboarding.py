"""Shared destination, explicit source import, no source-browser mutation."""
import json
import time
from unittest.mock import Mock

import pytest

from agent_reach.runtime import browser, cdp, state
from agent_reach.runtime.result import ReachError


def _cookie(domain, name="session", **extra):
    return {"name": name, "value": "test-value", "domain": domain, "path": "/", **extra}


def test_import_filters_other_sites_and_expired_cookies_before_browser_access(monkeypatch, tmp_path):
    source = tmp_path / "session.json"
    source.write_text(json.dumps({"cookies": [_cookie(".xiaohongshu.com"), _cookie(".example.com"),
        _cookie(".xiaohongshu.com", "expired", expires=time.time()-1)]}))
    start = Mock()
    monkeypatch.setattr(browser, "ensure_running", start)
    jar = []
    def call(method, params=None):
        if method == "Storage.setCookies":
            jar.extend(params["cookies"])
            return {}
        return {"cookies": jar}
    monkeypatch.setattr(cdp, "call", call)
    result = browser.import_session("xiaohongshu", state_file=source)
    assert result["imported_cookies"] == 1 and result["logged_in"] is None
    assert result["original_browser_changed"] is False and start.call_count == 1
    assert json.loads(source.read_text())["cookies"][0]["value"] == "test-value"
    assert len(json.loads((browser.browser_root()/"session.json").read_text())["cookies"]) == 1
    assert not state.load().get("reuse_sources")


def test_import_with_no_matching_cookies_does_not_launch(monkeypatch, tmp_path):
    source = tmp_path / "session.json"
    source.write_text(json.dumps([_cookie(".example.com")]))
    monkeypatch.setattr(browser, "ensure_running", lambda: pytest.fail("unusable import opened browser"))
    with pytest.raises(ReachError, match="No unexpired"):
        browser.import_session("xiaohongshu", state_file=source)


def test_import_requires_exactly_one_explicit_source():
    with pytest.raises(ReachError, match="exactly one"):
        browser.import_session("xiaohongshu")
    with pytest.raises(ReachError, match="exactly one"):
        browser.import_session("xiaohongshu", state_file="x", opencli_profile="y")


def test_source_export_is_scoped_to_selected_site(monkeypatch):
    from agent_reach.backends import opencli
    export = Mock(return_value=[_cookie(".xiaohongshu.com")])
    monkeypatch.setattr(opencli, "export_site_cookies", export)
    monkeypatch.setattr(browser, "ensure_running", lambda: None)
    monkeypatch.setattr(cdp, "call", lambda *a, **k: {})
    browser.import_session("xiaohongshu", opencli_profile="user-selected")
    export.assert_called_once_with("user-selected", "xiaohongshu.com")


def test_unmanaged_debugging_port_is_never_closed_or_navigated(monkeypatch):
    monkeypatch.setattr(browser, "is_running", lambda: True)
    monkeypatch.setattr(browser, "watcher_running", lambda: False)
    monkeypatch.setattr(browser, "_profile_pids", lambda: [])
    monkeypatch.setattr(cdp, "call", lambda *a, **k: pytest.fail("touched unrelated browser"))
    for operation in (browser.ensure_running, browser.stop, lambda: browser.start("https://example.com")):
        with pytest.raises(ReachError, match="unmanaged"):
            operation()


def test_owned_snapshot_migration_preserves_a_newer_shared_login(monkeypatch):
    source=state.root()/"sessions/xiaohongshu-cloak/profile/reach-session.json"
    source.parent.mkdir(parents=True)
    source.write_text(json.dumps({"cookies":[_cookie(".xiaohongshu.com", "auth"),_cookie(".xiaohongshu.com", "extra")]}))
    jar=[{**_cookie(".xiaohongshu.com","auth"),"value":"newer-login"}]
    def call(method,params=None,**kwargs):
        if method=="Storage.setCookies":
            jar.extend(params["cookies"])
            return {}
        return {"cookies":list(jar)}
    monkeypatch.setattr(browser,"ensure_running",lambda:None)
    monkeypatch.setattr(cdp,"call",call)
    browser.migrate_owned_session("xiaohongshu")
    browser.migrate_owned_session("xiaohongshu")
    assert next(c for c in jar if c["name"]=="auth")["value"]=="newer-login"
    assert len(jar)==2 and source.exists()
    assert state.load()["session_migrations"]["xiaohongshu"]["imported_cookies"]==1


def test_logout_cannot_reimport_an_old_owned_snapshot(monkeypatch, capsys):
    from agent_reach.runtime import cli
    old = state.root() / "sessions/xiaohongshu-cloak/profile/reach-session.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"cookies": [_cookie(".xiaohongshu.com")]}))
    state.mutate(lambda saved: saved.update(reuse_sources={"xiaohongshu": {"profile": "old"}}))
    clear = Mock(return_value=1)
    monkeypatch.setattr(browser, "clear_site", clear)
    assert cli.main(["logout", "xiaohongshu"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"]
    clear.assert_called_once_with(["xiaohongshu.com"])
    assert not old.exists() and not state.load()["reuse_sources"]
    monkeypatch.setattr(browser, "import_session", lambda *a, **k: pytest.fail("revived logged-out session"))
    browser.migrate_owned_session("xiaohongshu")


@pytest.mark.parametrize("shim", [False, True])
def test_source_export_locates_the_unmodified_page_api_for_npm_layouts(monkeypatch, tmp_path, shim):
    from agent_reach.backends.opencli import export_site_cookies
    from agent_reach.runtime import run, tools
    package = tmp_path / "node_modules/@jackwener/opencli"
    page = package / "dist/src/browser/page.js"
    page.parent.mkdir(parents=True)
    page.write_text("// upstream fixture")
    entry = tmp_path / "opencli.cmd" if shim else package / "dist/src/main.js"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("shim or upstream entry")
    monkeypatch.setattr(tools, "resolve", lambda _: str(entry))
    call = Mock(return_value="[]")
    monkeypatch.setattr(run, "run_cmd", call)
    assert export_site_cookies("chosen-profile", "xiaohongshu.com") == []
    argv = call.call_args.args[0]
    assert page.as_uri() in argv[3] and argv[-2:] == ["chosen-profile", "xiaohongshu.com"]
    assert page.read_text() == "// upstream fixture"
