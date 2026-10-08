# -*- coding: utf-8 -*-
"""Management commands: private installs, add/remove, doctor, watch, uninstall, update, skill."""

import json

import pytest

from agent_reach.channels.base import Action, Channel, Param
from agent_reach.runtime import browser, manage, state, tools
from agent_reach.runtime.result import ReachError
from agent_reach.utils.paths import home_dir


class _Base(Channel):
    description = "x"
    passes = True

    def can_handle(self, url):
        return False

    def _go(self, **kw):
        if not type(self).passes:
            raise ReachError("UPSTREAM_BROKEN", "down")
        return [{"title": "ok"}]


def _actions():
    return (Action("search", "s", (Param("query", "q"),), (("b", "_go"),), live_test={"query": "x"}),)


class Web(_Base):
    name, level, actions = "web", "default", _actions()


class Bili(_Base):
    name, level, actions, tools = "bili", "optional", _actions(), ("bili-cli",)


class Bili2(_Base):
    name, level, actions, tools = "bili2", "optional", _actions(), ("bili-cli",)


class Needy(_Base):
    name, level, actions, prereqs = "needy", "optional", _actions(), ("x",)


@pytest.fixture
def env(monkeypatch):
    chans = [Web(), Bili(), Bili2(), Needy()]
    monkeypatch.setattr(manage, "_channels", lambda: chans)
    monkeypatch.setitem(manage.PREREQS, "x", {"check": lambda: False, "hint": "install x"})
    installs = []

    def fake_install(tool, *, global_=False):
        installs.append((tool.name, global_))
        if not global_:
            b = tools._private_bin(tool, tool.commands[0])
            b.parent.mkdir(parents=True, exist_ok=True)
            b.write_text("")

    monkeypatch.setattr(tools, "_install", fake_install)
    monkeypatch.setattr(browser, "is_running", lambda: False)
    return {"chans": chans, "installs": installs}


# ── private installs ──


def test_private_copy_wins_over_path(env, monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda c: "/usr/bin/" + c)
    assert tools.resolve("bili") == "/usr/bin/bili"
    tools.ensure("bili-cli")
    assert tools.resolve("bili") == str(tools._private_bin(tools.TOOLS["bili-cli"], "bili"))


def test_private_install_is_recorded_as_ours_and_not_repeated(env):
    assert tools.ensure("bili-cli")["owner"] == "agent-reach"
    tools.ensure("bili-cli")
    assert env["installs"] == [("bili-cli", False)]


@pytest.mark.parametrize(
    "user_version, allow, expect_install, expect_owner",
    [("1.9.0", False, False, "user"), ("1.8.0", True, True, "user"), (None, False, True, "agent-reach")],
)
def test_singleton_reuses_user_copy_and_upgrades_only_with_consent(
    env, monkeypatch, user_version, allow, expect_install, expect_owner
):
    monkeypatch.setattr(tools, "installed_version", lambda t: user_version)
    entry = tools.ensure("opencli", allow_upgrade=allow)
    assert entry["owner"] == expect_owner and entry["scope"] == "global"
    assert (env["installs"] == [("opencli", True)]) is expect_install


def test_singleton_too_old_without_consent_changes_nothing(env, monkeypatch):
    monkeypatch.setattr(tools, "installed_version", lambda t: "1.0.0")
    with pytest.raises(ReachError) as info:
        tools.ensure("opencli")
    assert info.value.code == "NEED_SETUP" and "--allow-upgrade" in info.value.hint
    assert env["installs"] == []


# ── add / remove ──


def test_add_with_missing_prerequisite_installs_nothing(env):
    with pytest.raises(ReachError) as info:
        manage.add("needy")
    assert info.value.code == "NEED_SETUP" and "install x" in info.value.hint
    assert "needy" not in state.load()["channels"]


def test_remove_keeps_tool_still_used_by_another_channel(env):
    manage.add("bili")
    manage.add("bili2")
    assert manage.remove("bili")["removed_tools"] == []
    assert tools.resolve("bili") is not None
    assert manage.remove("bili2")["removed_tools"] == ["bili-cli"]
    assert not tools.tool_dir("bili-cli").exists()


def test_default_channels_cannot_be_removed(env):
    with pytest.raises(ReachError):
        manage.remove("web")


# ── doctor / watch ──


def _status(name):
    return next(c for c in manage.doctor()["channels"] if c["channel"] == name)["status"]


def test_doctor_states(env):
    assert _status("bili") == "not_added"
    manage.add("bili")
    assert _status("bili") == "unverified"
    manage.run_checks(["bili"])
    assert _status("bili") == "ready"
    Bili.passes = False
    try:
        manage.run_checks(["bili"])
        assert _status("bili") == "broken"
    finally:
        Bili.passes = True
    data = state.load()
    data["checks"]["bili"]["at"] = "2000-01-01T00:00:00Z"
    state.save(data)
    assert _status("bili") == "unverified"


def test_doctor_reports_missing_tool_as_needs_setup(env, monkeypatch):
    monkeypatch.setattr(tools.shutil, "which", lambda c: None)
    manage.add("bili")
    tools.remove_private("bili-cli")
    assert _status("bili") == "needs_setup"


def test_watch_reports_only_what_broke_since_last_check(env, monkeypatch):
    monkeypatch.setattr(manage, "update_check", lambda quiet=False: {"update_available": False})
    manage.add("bili")
    assert manage.watch()["all_good"] is True
    Bili.passes = False
    try:
        result = manage.watch()
        assert result["regressions"] == [{"channel": "bili", "action": "search"}]
        assert manage.watch()["regressions"] == [], "an already-broken channel is not reported again"
    finally:
        Bili.passes = True


# ── uninstall ──


def test_uninstall_removes_only_what_we_own(env):
    manage.add("bili")
    root = state.root()
    (root / "config.yaml").write_text("x: 1")
    (root / "my-notes").mkdir()
    (root / "tools" / "someone-elses-tool").mkdir(parents=True)
    dry = manage.uninstall(dry_run=True)
    assert (root / "state.json").exists(), "dry run changes nothing"
    assert str(tools.tool_dir("bili-cli")) in dry["removed"]
    manage.uninstall()
    assert not (root / "state.json").exists() and not (root / "config.yaml").exists()
    assert not tools.tool_dir("bili-cli").exists()
    assert (root / "my-notes").exists() and (root / "tools" / "someone-elses-tool").exists()


def test_uninstall_refuses_while_browser_open(env, monkeypatch):
    monkeypatch.setattr(browser, "is_running", lambda: True)
    with pytest.raises(ReachError):
        manage.uninstall()


# ── update ──


@pytest.mark.parametrize("latest, available", [("v2.0.1", True), ("v2.0.0", False), ("v1.9.9", False)])
def test_update_check_compares_versions(monkeypatch, latest, available):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"tag_name": latest}).encode()

    monkeypatch.setattr(manage, "__version__", "2.0.0")
    monkeypatch.setattr(manage.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert manage.update_check()["update_available"] is available


@pytest.mark.parametrize("method, head", [("uv", ["uv", "tool"]), ("pipx", ["pipx", "install"])])
def test_upgrade_uses_the_same_installer_as_the_original_install(method, head):
    cmd = manage.upgrade_command(method, "2.0.1")
    assert cmd[:2] == head and cmd[-1].endswith("/v2.0.1.zip")


# ── skill ──


def test_skill_lists_every_channel_and_has_no_placeholders(env):
    for lang in ("zh", "en"):
        text = manage.render_skill(lang)
        assert "{{" not in text
        for ch in env["chans"]:
            assert f"| {ch.name} |" in text


def test_skill_install_replaces_old_instructions(env):
    old = home_dir() / ".claude" / "skills" / "agent-reach"
    (old / "references").mkdir(parents=True)
    (old / "references" / "social.md").write_text("old")
    assert str(old) in manage.install_skill()
    assert (old / "SKILL.md").exists() and not (old / "references").exists()


# ── configure ──


def test_configure_saves_known_keys_only(env):
    from agent_reach.config import Config

    manage.configure("groq-key", "gsk_test")
    assert Config(read_only=True).get("groq_api_key") == "gsk_test"
    with pytest.raises(ReachError):
        manage.configure("twitter-cookies", "x")


def test_doctor_separates_needs_login_from_broken(env, monkeypatch):
    def need_login(self, **kw):
        raise ReachError("NEED_LOGIN", "log in")

    monkeypatch.setattr(Bili, "_go", need_login)
    manage.add("bili")
    manage.run_checks(["bili"])
    assert _status("bili") == "needs_login"
