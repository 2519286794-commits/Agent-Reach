"""Agent Reach dedicated browser: extension, Chrome for Testing, cookies, CDP pipe (no real Chrome)."""

import json
import os
import shutil
import threading
import zipfile

import pytest

from agent_reach.runtime import browser, cdp, tools


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(browser, "is_running", lambda: False)
    return tmp_path


def _zip(path, files):
    with zipfile.ZipFile(path, "w") as zf:
        for name, (data, mode) in files.items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o100000 | mode) << 16
            zf.writestr(info, data)
    return path


def _fake_downloads(monkeypatch, index: dict, archives: dict):
    monkeypatch.setattr(browser, "_fetch", lambda url, timeout=30.0: json.dumps(index[url]).encode())
    monkeypatch.setattr(browser, "_download", lambda url, dest, timeout=60.0: shutil.copy(archives[url], dest))


def test_domain_match_is_exact_or_subdomain():
    assert cdp.domain_matches(".reddit.com", "reddit.com")
    assert cdp.domain_matches("www.reddit.com", "reddit.com")
    assert not cdp.domain_matches("notreddit.com", "reddit.com")


def test_extension_installs_at_a_stable_path_and_refreshes_only_on_new_release(home, monkeypatch, tmp_path):
    manifest = lambda v: (json.dumps({"manifest_version": 3, "version": v}), 0o644)  # noqa: E731
    v1 = _zip(tmp_path / "v1.zip", {"manifest.json": manifest("1.0.1"), "dist/background.js": ("//", 0o644)})
    v2 = _zip(tmp_path / "v2.zip", {"manifest.json": manifest("1.0.2")})
    release = {"assets": [{"name": "opencli-extension-v1.0.1.zip", "browser_download_url": "u1"}]}
    _fake_downloads(monkeypatch, {browser.OPENCLI_RELEASE_API: release}, {"u1": v1, "u2": v2})

    assert browser.refresh_extension() == {"version": "1.0.1", "updated": True}
    assert (browser.extension_dir() / "dist" / "background.js").is_file()
    assert browser.refresh_extension() == {"version": "1.0.1", "updated": False}

    release["assets"] = [{"name": "opencli-extension-v1.0.2.zip", "browser_download_url": "u2"}]
    assert browser.refresh_extension() == {"version": "1.0.2", "updated": True}
    assert browser.extension_version() == "1.0.2"
    assert browser._load_state()["extension_version"] == "1.0.2"


def test_extension_refresh_offline_keeps_the_current_copy(home, monkeypatch):
    browser.extension_dir().mkdir(parents=True)
    (browser.extension_dir() / "manifest.json").write_text(json.dumps({"version": "1.0.0"}))

    def offline(url, timeout=30.0):
        raise OSError("offline")

    monkeypatch.setattr(browser, "_fetch", offline)
    assert browser.refresh_extension() == {"version": "1.0.0", "updated": False}


def test_ensure_chrome_installs_chrome_for_testing_when_system_has_none(home, monkeypatch, tmp_path):
    archive = _zip(tmp_path / "cft.zip", {"chrome-linux64/chrome": ("#!/bin/sh\n", 0o755)})
    index = {"channels": {"Stable": {"version": "155.0.1", "downloads": {"chrome": [
        {"platform": "linux64", "url": "cft-url"}]}}}}
    _fake_downloads(monkeypatch, {browser.CFT_VERSIONS_URL: index}, {"cft-url": archive})
    monkeypatch.setattr(browser, "_system_chrome", lambda: None)
    monkeypatch.setattr(browser, "_cft_platform", lambda: "linux64")
    recorded = []
    monkeypatch.setattr(tools, "record", lambda name, version: recorded.append((name, version)), raising=False)

    assert browser.chrome_binary() is None  # never downloads by itself
    exe = browser.ensure_chrome()
    assert exe == str(tools.tool_dir("chrome") / "chrome-linux64" / "chrome")
    assert os.access(exe, os.X_OK)
    assert browser.chrome_binary() == exe
    assert recorded == [("chrome", "155.0.1")]
    assert browser.ensure_chrome() == exe and len(recorded) == 1  # second call: no download


def test_ensure_chrome_prefers_system_chrome(home, monkeypatch):
    monkeypatch.setattr(browser, "_system_chrome", lambda: "/sys/chrome")
    monkeypatch.setattr(browser, "_fetch", lambda *a, **k: pytest.fail("must not download"))
    assert browser.ensure_chrome() == "/sys/chrome"


def test_clear_site_expires_only_that_sites_cookies(home, monkeypatch):
    jar = [
        {"name": "a", "value": "1", "domain": ".reddit.com", "path": "/"},
        {"name": "b", "value": "2", "domain": "www.reddit.com", "path": "/"},
        {"name": "c", "value": "3", "domain": "notreddit.com", "path": "/"},
    ]

    def fake_call(method, params=None):
        if method == "Storage.getCookies":
            return {"cookies": list(jar)}
        if method == "Storage.setCookies":
            for c in params["cookies"]:
                assert c["expires"] == 1
                jar[:] = [j for j in jar if (j["name"], j["domain"]) != (c["name"], c["domain"])]
            return {}
        raise AssertionError(method)

    browser.profile_dir().mkdir(parents=True)
    monkeypatch.setattr(browser, "ensure_running", lambda context=None: None)
    monkeypatch.setattr(cdp, "call", fake_call)
    assert browser.clear_site(["reddit.com"]) == 2
    assert [c["name"] for c in jar] == ["c"]


def test_clear_site_never_opens_a_browser_that_was_never_used(home, monkeypatch):
    monkeypatch.setattr(browser, "ensure_running", lambda context=None: pytest.fail("opened the browser"))
    assert browser.clear_site(["reddit.com"]) == 0


def test_delete_profile_removes_the_browser_folder(home, monkeypatch):
    monkeypatch.setattr(browser, "stop", lambda timeout=10.0: True)
    browser.profile_dir().mkdir(parents=True)
    browser.touch()
    assert browser.delete_profile() is True
    assert not browser.browser_root().exists()
    assert browser.delete_profile() is False


def test_pipe_connection_matches_replies_and_notices_close():
    to_chrome_r, to_chrome_w = os.pipe()
    from_chrome_r, from_chrome_w = os.pipe()

    def fake_chrome():  # echoes each NUL-delimited command back as a reply, with an event first
        buf = b""
        while True:
            chunk = os.read(to_chrome_r, 4096)
            if not chunk:
                break
            buf += chunk
            while b"\0" in buf:
                raw, buf = buf.split(b"\0", 1)
                msg = json.loads(raw)
                os.write(from_chrome_w, json.dumps({"method": "Some.event"}).encode() + b"\0")
                os.write(from_chrome_w, json.dumps({"id": msg["id"], "result": {"id": msg["params"]["path"]}}).encode() + b"\0")
        os.close(from_chrome_w)  # Chrome exits when its input pipe closes
        os.close(to_chrome_r)

    t = threading.Thread(target=fake_chrome)
    t.start()
    conn = cdp.PipeConnection(to_chrome_w, from_chrome_r)
    assert conn.call("Extensions.loadUnpacked", {"path": "/ext"}) == {"id": 1, "result": {"id": "/ext"}}
    assert conn.call("Extensions.loadUnpacked", {"path": "/two"})["result"] == {"id": "/two"}
    conn.close()
    t.join(5)
    assert conn.closed.is_set()
    assert "error" in conn.call("Browser.close", timeout=1)
