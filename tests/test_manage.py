# -*- coding: utf-8 -*-
"""Management commands: private installs, add/remove, setup, doctor, uninstall, update, skill."""

import json
import os

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
    stopped = []
    monkeypatch.setattr(browser, "is_running", lambda: False)
    monkeypatch.setattr(browser, "stop", lambda: stopped.append(True), raising=False)
    return {"chans": chans, "installs": installs, "stopped": stopped}


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


# ── doctor ──


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


def test_check_without_names_tests_only_default_and_added_channels(env):
    manage.add("bili")
    tested = {r["channel"] for r in manage.run_checks()["results"]}
    assert tested == {"web", "bili"}


def test_doctor_marks_regressed_only_when_the_previous_check_passed(env):
    manage.add("bili")
    manage.run_checks(["bili"])
    assert _doctor("bili")["regressed"] is False
    Bili.passes = False
    try:
        manage.run_checks(["bili"])
        assert _doctor("bili")["regressed"] is True
        manage.run_checks(["bili"])
        assert _doctor("bili")["regressed"] is False, "an already-broken channel is not a regression"
    finally:
        Bili.passes = True


def _doctor(name):
    return next(c for c in manage.doctor()["channels"] if c["channel"] == name)


# ── setup ──


class Broken(_Base):
    name, level, actions, tools = "broken", "default", _actions(), ("bili-cli",)
    login_argv = ("bili", "login")


def test_setup_adds_default_channels_and_survives_a_failing_install(env, monkeypatch):
    env["chans"].append(Broken())

    def failing_install(tool, *, global_=False):
        raise ReachError("UPSTREAM_BROKEN", "install failed: no network")

    monkeypatch.setattr(tools, "_install", failing_install)
    result = manage.setup()
    by_name = {c["channel"]: c for c in result["default_channels"]}
    assert set(by_name) == {"web", "broken"}
    assert by_name["web"]["ok"] is True
    assert by_name["broken"]["ok"] is False and by_name["broken"]["error"]["code"] == "UPSTREAM_BROKEN"
    assert result["prerequisites"] == {}, "only prerequisites of default channels are reported"
    assert result["logins"] == [{"channel": "broken", "command": "agent-reach login broken"}]
    assert {c["channel"] for c in result["optional_channels"]} == {"bili", "bili2", "needy"}
    assert result["skill"]["installed"] is True


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
    assert env["stopped"] == []
    manage.uninstall()
    assert not (root / "state.json").exists() and not (root / "config.yaml").exists()
    assert not tools.tool_dir("bili-cli").exists()
    assert (root / "my-notes").exists() and (root / "tools" / "someone-elses-tool").exists()


def test_uninstall_closes_the_browser_instead_of_refusing(env):
    manage.uninstall()
    assert env["stopped"] == [True]


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


def test_upgrade_reinstalls_the_release_with_uv():
    cmd = manage.upgrade_command("2.0.1")
    assert cmd[:4] == ["uv", "tool", "install", "--force"] and cmd[-1].endswith("/v2.0.1.zip")


def test_update_from_a_non_uv_install_asks_for_one_uv_reinstall(monkeypatch):
    monkeypatch.setattr(manage, "update_check", lambda: {"current": "2.0.0", "latest": "2.0.1",
                                                         "update_available": True})
    monkeypatch.setattr(manage, "install_method", lambda: "other")
    monkeypatch.setattr(manage.subprocess, "run", lambda *a, **k: pytest.fail("must not run an installer"))
    with pytest.raises(ReachError) as info:
        manage.update()
    assert "uv tool install --force" in info.value.hint


# ── skill ──


def test_skill_lists_every_channel_and_has_no_placeholders(env):
    for lang in ("zh", "en"):
        text = manage.render_skill(lang)
        assert "{{" not in text
        for ch in env["chans"]:
            assert f"| {ch.name} |" in text


def _seed_our_copy(path):
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text("---\nname: agent-reach\ndescription: old\n---\nold\n")
    (path / "references").mkdir()


def test_skill_one_real_copy_linked_only_for_present_ais(env):
    home = home_dir()
    for d in (".claude", ".codex", ".openclaw"):
        (home / d).mkdir()
    result = manage.place_skill()
    real = home / ".agents" / "skills" / "agent-reach"
    assert (real / "SKILL.md").is_file()
    for link in (home / ".claude" / "skills" / "agent-reach", home / ".openclaw" / "skills" / "agent-reach"):
        assert link.is_symlink() and os.path.realpath(link) == os.path.realpath(real)
    assert not (home / ".codex" / "skills").exists(), "codex reads ~/.agents/skills itself"
    assert not (home / ".cursor").exists(), "absent AIs get nothing"
    assert set(result["agents"]) == {"claude-code", "codex", "openclaw"}
    assert len(state.load()["skill"]["links"]) == 2


def test_skill_replaces_our_old_copy_but_not_a_foreign_one(env):
    home = home_dir()
    ours = home / ".claude" / "skills" / "agent-reach"
    _seed_our_copy(ours)
    foreign = home / ".cursor" / "skills" / "agent-reach"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("---\nname: someone-else\n---\n")
    native_old = home / ".codex" / "skills" / "agent-reach"
    _seed_our_copy(native_old)
    result = manage.place_skill()
    assert ours.is_symlink()
    assert not foreign.is_symlink() and "someone-else" in (foreign / "SKILL.md").read_text()
    assert [n["agent"] for n in result["not_linked"]] == ["cursor"]
    assert not native_old.exists() and result["removed_old_copies"] == [str(native_old)]


def test_skill_falls_back_to_a_copy_without_symlink_rights(env, monkeypatch):
    home = home_dir()
    (home / ".claude").mkdir()

    def no_symlinks(self, *a, **k):
        raise OSError("symlinks not permitted")

    monkeypatch.setattr(type(home), "symlink_to", no_symlinks)
    result = manage.place_skill()
    copy = home / ".claude" / "skills" / "agent-reach"
    assert not copy.is_symlink() and (copy / "SKILL.md").is_file()
    assert result["copies"] == [str(copy)] and result["links"] == []
    (copy / "SKILL.md").write_text("---\nname: agent-reach\n---\nstale\n")
    manage.place_skill()
    assert "stale" not in (copy / "SKILL.md").read_text(), "update refreshes recorded copies"
    manage.uninstall()
    assert not copy.exists()


def test_skill_link_for_an_unlisted_ai_and_uninstall_removes_everything(env):
    home = home_dir()
    (home / ".claude").mkdir()
    manage.place_skill()
    other = home / "my-ai" / "skills"
    manage.link_skill(str(other))
    assert (other / "agent-reach").is_symlink()
    stray = home / ".gemini" / "skills" / "agent-reach"
    stray.parent.mkdir(parents=True)
    stray.symlink_to(home / ".agents" / "skills" / "agent-reach")
    manage.place_skill()
    assert (other / "agent-reach").is_symlink(), "update keeps recorded links"
    manage.uninstall()
    for p in (other / "agent-reach", home / ".claude" / "skills" / "agent-reach", stray,
              home / ".agents" / "skills" / "agent-reach"):
        assert not p.exists() and not p.is_symlink()


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
