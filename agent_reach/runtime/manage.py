"""Management commands: setup, add, remove, update, doctor, watch, uninstall, configure.

Each public function returns a plain dict `result` or raises ReachError; the CLI
wraps it in {schema_version, ok, action, result, error}.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from agent_reach import __version__

from . import state, tools
from .result import BAD_INPUT, NEED_SETUP, UPSTREAM_BROKEN, ReachError

REPO = "Panniantong/Agent-Reach"
CHECK_FRESH_SECONDS = 24 * 3600



def _chrome_present() -> bool:
    from .browser import chrome_binary

    return chrome_binary() is not None


def home_dir_skills() -> Path:
    """Fallback skill root when no agent's skill directory exists yet."""
    from agent_reach.utils.paths import home_dir

    return home_dir() / ".agents" / "skills"
# ── prerequisites we only check and explain ──

PREREQS: Dict[str, dict] = {
    "node": {"check": lambda: bool(shutil.which("node") and shutil.which("npm")),
             "hint": "Install Node.js: https://nodejs.org (macOS: brew install node)"},
    "git": {"check": lambda: bool(shutil.which("git")), "hint": "Install git (macOS: xcode-select --install)"},
    "chrome": {"check": lambda: _chrome_present(), "hint": "Install Google Chrome: https://www.google.com/chrome"},
    "ffmpeg": {"check": lambda: bool(shutil.which("ffmpeg")), "hint": "Install ffmpeg (macOS: brew install ffmpeg)"},
    "uv": {"check": lambda: bool(shutil.which("uvx")),
           "hint": "Install uv: https://docs.astral.sh/uv/getting-started/installation/"},
}


def _channels():
    from .cli import unified_channels

    return unified_channels()


def _channel(name: str):
    ch = next((c for c in _channels() if c.name == name), None)
    if ch is None:
        valid = ", ".join(c.name for c in _channels())
        raise ReachError(BAD_INPUT, f"unknown channel: {name}; valid: {valid}")
    return ch


def is_added(ch, data: Optional[dict] = None) -> bool:
    return ch.level == "default" or ch.name in (data or state.load())["channels"]


def missing_prereqs(ch) -> List[str]:
    return [p for p in ch.prereqs if not PREREQS[p]["check"]()]


# ── checks ──

def run_checks(names: Optional[List[str]] = None, timeout: float = 60.0) -> dict:
    """Live-test every backend of every action with a live_test; persist results in state."""
    from .dispatch import run_action

    selected = _channels()
    if names:
        unknown = set(names) - {c.name for c in selected}
        if unknown:
            raise ReachError(BAD_INPUT, f"unknown channel(s): {', '.join(sorted(unknown))}")
        selected = [c for c in selected if c.name in names]
    results = []
    for ch in selected:
        for action in ch.actions:
            if action.live_test is None:
                continue
            for label, _ in action.backends:
                out = run_action(ch, action.name, dict(action.live_test), timeout=timeout, only_backend=label)
                passed = bool(out["ok"] and out["items"])
                err = out["error"] or (None if passed else {"code": "EMPTY", "message": "succeeded but returned no items"})
                results.append({
                    "channel": ch.name, "action": action.name, "backend": label, "passed": passed,
                    "elapsed_ms": out["meta"]["elapsed_ms"],
                    "error": err and {"code": err["code"], "message": err["message"]},
                })
    by_action: Dict[tuple, bool] = {}
    codes: Dict[tuple, str] = {}
    for r in results:
        key = (r["channel"], r["action"])
        by_action[key] = by_action.get(key, False) or r["passed"]
        if not r["passed"] and key not in codes:
            codes[key] = r["error"]["code"]
    data = state.load()
    for ch in selected:
        actions = {a: ok for (c, a), ok in by_action.items() if c == ch.name}
        if actions:
            failed = {a: codes[(ch.name, a)] for a, ok in actions.items() if not ok}
            data["checks"][ch.name] = {"at": state.now(), "actions": actions, "codes": failed}
    state.save(data)
    return {"ok": bool(results) and all(by_action.values()), "results": results}


def channel_status(ch, data: dict) -> dict:
    if not is_added(ch, data):
        return {"status": "not_added", "problems": [], "hint": f"agent-reach add {ch.name}"}
    problems = [f"missing {p}: {PREREQS[p]['hint']}" for p in missing_prereqs(ch)]
    problems += [f"{t} not installed: run `agent-reach add {ch.name}`" for t in ch.tools
                 if not tools.resolve(tools.TOOLS[t].commands[0])]
    problems += ch.setup_problems()
    if problems:
        return {"status": "needs_setup", "problems": problems}
    check = data["checks"].get(ch.name)
    if check and state.age_seconds(check["at"]) < CHECK_FRESH_SECONDS:
        failed = [a for a, ok in check["actions"].items() if not ok]
        if failed:
            codes = check.get("codes", {})
            if all(codes.get(a) == "NEED_LOGIN" for a in failed):
                return {"status": "needs_login", "problems": [f"needs login for: {', '.join(failed)}"],
                        "hint": f"agent-reach login {ch.name}", "checked_at": check["at"]}
            return {"status": "broken", "problems": [f"live check failed: {', '.join(failed)}"], "checked_at": check["at"]}
        return {"status": "ready", "problems": [], "checked_at": check["at"]}
    return {"status": "unverified", "problems": [], "hint": f"agent-reach check {ch.name}"}


def doctor(live: bool = False) -> dict:
    if live:
        added = [c.name for c in _channels() if is_added(c)]
        run_checks(added)
    data = state.load()
    channels = []
    for ch in _channels():
        channels.append({"channel": ch.name, "level": ch.level, **channel_status(ch, data)})
    return {"version": __version__, "channels": channels}


def watch() -> dict:
    before = state.load()["checks"]
    added = [c.name for c in _channels() if is_added(c)]
    run_checks(added)
    after = state.load()["checks"]
    regressions = []
    for name, check in after.items():
        prev = before.get(name, {}).get("actions", {})
        for action, ok in check["actions"].items():
            if prev.get(action) and not ok:
                regressions.append({"channel": name, "action": action})
    upd = update_check(quiet=True)
    return {"regressions": regressions, "update": upd, "all_good": not regressions and not upd.get("update_available")}


# ── add / remove ──

def add(name: str, *, allow_upgrade: bool = False) -> dict:
    ch = _channel(name)
    if ch.level == "default":
        return {"channel": name, "added": True, "note": "default channel, always available"}
    missing = missing_prereqs(ch)
    if missing:
        raise ReachError(NEED_SETUP, f"missing prerequisites: {', '.join(missing)}",
                         hint="; ".join(PREREQS[p]["hint"] for p in missing))
    installed = [tools.ensure(t, allow_upgrade=allow_upgrade) for t in ch.tools]
    ch.on_add()
    data = state.load()
    data["channels"][name] = {"added_at": state.now()}
    state.save(data)
    nxt = list(ch.setup_problems())
    if ch.login_url or ch.login_argv or ch.logout_keys:
        nxt.append(f"log in: `agent-reach login {name}`")
    return {"channel": name, "added": True, "tools": installed, "next": nxt}


def remove(name: str) -> dict:
    ch = _channel(name)
    if ch.level == "default":
        raise ReachError(BAD_INPUT, f"{name} is a default channel and cannot be removed")
    from .sessions import clear_session

    data = state.load()
    was_added = data["channels"].pop(name, None) is not None
    data["checks"].pop(name, None)
    state.save(data)
    ch.on_remove()
    if ch.session:
        clear_session(ch.session)
    if ch.logout_keys:
        from agent_reach.config import Config

        cfg = Config()
        for key in ch.logout_keys:
            if cfg.get(key):
                cfg.delete(key)
    still_needed = {t for c in _channels() if c.name != name and is_added(c, data) for t in c.tools}
    removed_tools = [t for t in ch.tools if t not in still_needed and tools.remove_private(t)]
    return {"channel": name, "removed": was_added, "removed_tools": removed_tools}


# ── skill (the agent-facing instructions) ──

def skill_roots() -> List[Path]:
    from agent_reach.utils.paths import home_dir

    home = home_dir()
    roots = [home / ".agents" / "skills", home / ".claude" / "skills",
             home / ".config" / "opencode" / "skills", home / ".openclaw" / "skills"]
    oc = os.environ.get("OPENCLAW_HOME")
    if oc:
        roots.insert(0, Path(oc) / ".openclaw" / "skills")
    return roots


def _skill_lang() -> str:
    for var in ("AGENT_REACH_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "").strip().lower()
        if v.startswith("en"):
            return "en"
    return "zh"


def render_skill(lang: Optional[str] = None) -> str:
    from importlib.resources import files

    lang = lang or _skill_lang()
    template = files("agent_reach").joinpath("skill", "SKILL_en.md" if lang == "en" else "SKILL.md").read_text("utf-8")
    labels = {"default": "default", "optional": "optional", "experimental": "experimental"}
    rows = ["| channel | level | actions | login |", "|---|---|---|---|"]
    for ch in _channels():
        login = f"`agent-reach login {ch.name}`" if (ch.login_url or ch.login_argv or ch.logout_keys) else "-"
        rows.append(f"| {ch.name} | {labels[ch.level]} | {', '.join(a.name for a in ch.actions)} | {login} |")
    return template.replace("{{CHANNEL_TABLE}}", "\n".join(rows)).replace("{{VERSION}}", __version__)


def install_skill() -> List[str]:
    text = render_skill()
    roots = [r for r in skill_roots() if r.is_dir()] or [home_dir_skills()]
    written = []
    for root in roots:
        target = root / "agent-reach"
        if target.is_symlink():
            continue
        if target.exists():
            shutil.rmtree(target)  # old instructions are replaced, not merged
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text(text, encoding="utf-8")
        written.append(str(target))
    return written


def installed_skill_dirs() -> List[Path]:
    return [r / "agent-reach" for r in skill_roots() if (r / "agent-reach").exists() or (r / "agent-reach").is_symlink()]


# ── setup / migrate ──

def migrate() -> dict:
    """First run after an older Agent Reach: create state, keep credentials, suggest channels."""
    from agent_reach.config import Config

    cfg = Config(read_only=True)
    hints = []
    for cmd, channel in (("bili", "bilibili"), ("opencli", "xiaohongshu"), ("boss", "boss"), ("mcporter", "linkedin")):
        if shutil.which(cmd):
            hints.append(channel)
    if cfg.get("xueqiu_cookie"):
        hints.append("xueqiu")
    if cfg.get("groq_api_key"):
        hints.append("xiaoyuzhou")
    data = state.load()
    data["migrated_from"] = "pre-2.0"
    state.save(data)
    return {
        "migrated": True,
        "kept": "~/.agent-reach/config.yaml (keys and cookies unchanged)",
        "suggested_channels": sorted(set(hints)),
        "note": "Your own global tools were not removed. Old logins can be copied with `agent-reach login <channel> --import-existing`.",
    }


def setup() -> dict:
    prereqs = {p: PREREQS[p]["check"]() for p in PREREQS}
    migration = migrate() if not state.exists() and (state.root() / "config.yaml").exists() else None
    if not state.exists():
        state.save(state.load())
    skills = install_skill()
    optional = [
        {"channel": c.name, "level": c.level, "add": f"agent-reach add {c.name}",
         "needs": list(c.prereqs) + (["login"] if (c.login_url or c.login_argv) else [])}
        for c in _channels() if c.level != "default"
    ]
    return {
        "version": __version__,
        "default_channels": [c.name for c in _channels() if c.level == "default"],
        "prerequisites": {p: {"ok": ok, **({} if ok else {"hint": PREREQS[p]["hint"]})} for p, ok in prereqs.items()},
        "skill_installed": skills,
        "optional_channels": optional,
        "migration": migration,
    }


# ── update ──

def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except ValueError:
        return ()


def update_check(quiet: bool = False) -> dict:
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"User-Agent": "agent-reach", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            rel = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        if quiet:
            return {"current": __version__, "error": str(exc)[:200]}
        raise ReachError(UPSTREAM_BROKEN, f"could not reach GitHub: {exc}") from None
    latest = str(rel.get("tag_name", "")).lstrip("v")
    return {
        "current": __version__,
        "latest": latest,
        "update_available": _version_tuple(latest) > _version_tuple(__version__),
        "notes": (rel.get("body") or "")[:2000],
    }


def install_method() -> str:
    """How this copy of Agent Reach was installed: uv | pipx | pip | editable."""
    try:
        from importlib.metadata import distribution

        direct = distribution("agent-reach").read_text("direct_url.json") or "{}"
        if json.loads(direct).get("dir_info", {}).get("editable"):
            return "editable"
    except Exception:  # noqa: BLE001
        pass
    prefix = sys.prefix.replace("\\", "/")
    if "/uv/tools/" in prefix:
        return "uv"
    if "/pipx/venvs/" in prefix:
        return "pipx"
    return "pip"


def _source(version: str) -> str:
    return f"https://github.com/{REPO}/archive/refs/tags/v{version}.zip"


def upgrade_command(method: str, version: str) -> List[str]:
    src = _source(version)
    if method == "uv":
        return ["uv", "tool", "install", "--force", src]
    if method == "pipx":
        return ["pipx", "install", "--force", src]
    return [sys.executable, "-m", "pip", "install", "--upgrade", src]


def sync() -> dict:
    """After the program itself changed: bring tools to this version's pins, refresh the skill."""
    migration = migrate() if not state.exists() else None
    data = state.load()
    synced, problems = [], []
    for ch in _channels():
        if ch.level == "default" or ch.name not in data["channels"]:
            continue
        for t in ch.tools:
            try:
                synced.append(tools.ensure(t))
            except ReachError as err:
                problems.append({"tool": t, "code": err.code, "message": err.message, "hint": err.hint})
        ch.on_add()
    return {"version": __version__, "tools": synced, "problems": problems,
            "skill_installed": install_skill(), "migration": migration}


def update(check_only: bool = False) -> dict:
    info = update_check()
    if check_only:
        return info
    method = install_method()
    if info["update_available"] and method != "editable":
        cmd = upgrade_command(method, info["latest"])
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            raise ReachError(UPSTREAM_BROKEN, f"upgrade failed: {proc.stderr.strip()[-300:]}",
                             hint=f"Run manually: {' '.join(cmd)}")
        exe = shutil.which("agent-reach") or sys.argv[0]
        out = subprocess.run([exe, "update", "--sync-only"], capture_output=True, text=True, timeout=1800)
        try:
            synced = json.loads(out.stdout.strip().splitlines()[-1]).get("result")
        except (ValueError, IndexError):
            synced = {"raw": out.stdout[-500:]}
        return {**info, "upgraded": True, "method": method, "sync": synced}
    return {**info, "upgraded": False, "method": method, "sync": sync()}


# ── uninstall ──

_OWNED = ("config.yaml", "state.json", "mcporter.json", "sessions", "browser")


def uninstall(dry_run: bool = False) -> dict:
    from . import browser

    if browser.is_running() and not dry_run:
        raise ReachError(BAD_INPUT, "the Agent Reach browser is still open", hint="Close that Chrome window, then run uninstall again.")
    root = state.root()
    targets = [root / n for n in _OWNED]
    targets += [tools.tool_dir(n) for n in tools.TOOLS] + [root / "tools" / "xiaoyuzhou"]
    targets += installed_skill_dirs()
    targets = [t for t in targets if t.exists() or t.is_symlink()]
    globals_ = tools.uninstall_global_owned(dry_run=True)
    if not dry_run:
        tools.uninstall_global_owned(dry_run=False)
        for t in targets:
            if t.is_symlink() or t.is_file():
                t.unlink()
            else:
                shutil.rmtree(t)
        for d in (root / "tools", root):
            try:
                d.rmdir()
            except OSError:
                pass
    removing = {str(t) for t in targets} | {str(root / "tools")}
    kept = sorted(str(p) for p in root.iterdir() if str(p) not in removing) if root.exists() else []
    method = install_method()
    program = {"uv": "uv tool uninstall agent-reach", "pipx": "pipx uninstall agent-reach"}.get(
        method, f"{sys.executable} -m pip uninstall agent-reach")
    return {"dry_run": dry_run, "removed": [str(t) for t in targets], "global_tools_removed": globals_,
            "kept_unrecognized": kept, "remove_program": program}


# ── configure ──

CONFIG_KEYS = {"groq-key": "groq_api_key", "openai-key": "openai_api_key", "proxy": "proxy", "github-token": "github_token"}


def configure(key: str, value: str) -> dict:
    from agent_reach.config import Config

    if key not in CONFIG_KEYS:
        raise ReachError(BAD_INPUT, f"unknown key: {key}; valid: {', '.join(CONFIG_KEYS)}")
    if not value:
        raise ReachError(BAD_INPUT, "empty value")
    Config().set(CONFIG_KEYS[key], value)
    return {"key": key, "saved": True}
