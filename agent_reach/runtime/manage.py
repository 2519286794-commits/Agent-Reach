"""Management commands: setup, add, remove, update, doctor, skill, uninstall, configure.

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
from agent_reach.utils.paths import home_dir

from . import state, tools
from .result import BAD_INPUT, NEED_SETUP, UPSTREAM_BROKEN, ReachError

REPO = "Panniantong/Agent-Reach"
CHECK_FRESH_SECONDS = 24 * 3600


def _chrome_present() -> bool:
    from .browser import chrome_binary

    return chrome_binary() is not None


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


def _has_login(ch) -> bool:
    return bool(ch.login_url or ch.login_argv or ch.logout_keys)


# ── checks ──

def run_checks(names: Optional[List[str]] = None, timeout: float = 60.0) -> dict:
    """Live-test the added channels (or the named ones); persist results in state."""
    from .dispatch import run_action

    selected = _channels()
    if names:
        unknown = set(names) - {c.name for c in selected}
        if unknown:
            raise ReachError(BAD_INPUT, f"unknown channel(s): {', '.join(sorted(unknown))}")
        selected = [c for c in selected if c.name in names]
    else:
        data = state.load()
        selected = [c for c in selected if is_added(c, data)]
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
            previous = data["checks"].get(ch.name, {}).get("actions", {})
            data["checks"][ch.name] = {"at": state.now(), "actions": actions, "codes": failed, "previous": previous}
    state.save(data)
    return {"ok": bool(results) and all(by_action.values()), "results": results}


def regressed(check: Optional[dict]) -> bool:
    """An action passed in the previous check and fails in the latest one."""
    if not check:
        return False
    previous = check.get("previous", {})
    return any(previous.get(a) and not ok for a, ok in check.get("actions", {}).items())


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


def doctor() -> dict:
    """Status of every channel from local state only (no network); `check` runs the live tests."""
    data = state.load()
    channels = []
    for ch in _channels():
        channels.append({"channel": ch.name, "level": ch.level, **channel_status(ch, data),
                         "regressed": regressed(data["checks"].get(ch.name))})
    return {"version": __version__, "channels": channels}


# ── add / remove ──

def add(name: str, *, allow_upgrade: bool = False) -> dict:
    ch = _channel(name)
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
    if _has_login(ch):
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
#
# One real copy in ~/.agents/skills/agent-reach (read natively by Codex, OpenCode,
# Cline, Warp, Zed). AIs that do not read that folder get a symlink in their own
# skills folder, but only when their config folder exists. Source for the folders:
# the vercel-labs/skills supported-agents table.

SKILL_NAME = "agent-reach"


def _openclaw_home() -> Path:
    oc = os.environ.get("OPENCLAW_HOME")
    return (Path(oc) if oc else home_dir()) / ".openclaw"


def _config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) if xdg else home_dir() / ".config"


def linked_agents() -> Dict[str, tuple]:
    """AIs that need a link: name -> (config folder that proves it is installed, its skills folder)."""
    home = home_dir()
    return {
        "claude-code": (home / ".claude", home / ".claude" / "skills"),
        "openclaw": (_openclaw_home(), _openclaw_home() / "skills"),
        "hermes": (home / ".hermes", home / ".hermes" / "skills"),
        "cursor": (home / ".cursor", home / ".cursor" / "skills"),
        "gemini-cli": (home / ".gemini", home / ".gemini" / "skills"),
        "github-copilot": (home / ".copilot", home / ".copilot" / "skills"),
        "windsurf": (home / ".codeium" / "windsurf", home / ".codeium" / "windsurf" / "skills"),
    }


def native_agents() -> Dict[str, tuple]:
    """AIs that read ~/.agents/skills themselves: name -> (config folder, their own old skills folder)."""
    home = home_dir()
    return {
        "codex": (home / ".codex", home / ".codex" / "skills"),
        "opencode": (_config_home() / "opencode", _config_home() / "opencode" / "skills"),
    }


def skill_dir() -> Path:
    return home_dir() / ".agents" / "skills" / SKILL_NAME


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
        login = f"`agent-reach login {ch.name}`" if _has_login(ch) else "-"
        rows.append(f"| {ch.name} | {labels[ch.level]} | {', '.join(a.name for a in ch.actions)} | {login} |")
    return template.replace("{{CHANNEL_TABLE}}", "\n".join(rows)).replace("{{VERSION}}", __version__)


def _is_our_copy(path: Path) -> bool:
    """A real folder holding our SKILL.md (frontmatter `name: agent-reach`)."""
    if path.is_symlink() or not path.is_dir():
        return False
    try:
        lines = (path / "SKILL.md").read_text("utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return False
    if not lines or lines[0].strip() != "---":
        return False
    for line in lines[1:]:
        if line.strip() == "---":
            return False
        key, _, value = line.partition(":")
        if key.strip() == "name":
            return value.strip().strip("'\"") == SKILL_NAME
    return False


def _links_to_real(path: Path) -> bool:
    if not path.is_symlink():
        return False
    try:
        return Path(os.path.realpath(path)) == Path(os.path.realpath(skill_dir()))
    except OSError:
        return False


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _write_real_copy(text: str) -> Path:
    real = skill_dir()
    _remove(real)  # old instructions are replaced, not merged
    real.mkdir(parents=True)
    (real / "SKILL.md").write_text(text, encoding="utf-8")
    return real


def _write_copy(target: Path, text: str) -> None:
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text(text, encoding="utf-8")


def _link_into(skills_dir: Path, text: str) -> tuple:
    """Make `<skills_dir>/agent-reach` point at the real copy.

    Returns (kind, reason): kind is "link" | "copy" | None (left alone; reason says why).
    Our own old real copy is replaced; anything else already there is left untouched.
    """
    target = skills_dir / SKILL_NAME
    if _links_to_real(target):
        return "link", None
    if target.is_symlink():
        return None, f"a symlink to {os.readlink(target)} is already there"
    if target.exists():
        if not _is_our_copy(target):
            return None, "a different skill named agent-reach is already there"
        shutil.rmtree(target)
    skills_dir.mkdir(parents=True, exist_ok=True)
    try:
        target.symlink_to(skill_dir(), target_is_directory=True)
        return "link", None
    except (OSError, NotImplementedError):
        # Windows without symlink rights: fall back to a copy that update refreshes.
        _write_copy(target, text)
        return "copy", None


def _remove_native_old_copies() -> List[str]:
    """Our old real copies in folders of AIs that now read ~/.agents/skills (so they don't see two)."""
    removed = []
    for _, skills in native_agents().values():
        target = skills / SKILL_NAME
        if _is_our_copy(target):
            shutil.rmtree(target)
            removed.append(str(target))
    return removed


def _agent_for(skills_dir: Path) -> str:
    return next((name for name, (_, d) in linked_agents().items() if d == skills_dir), "custom")


def place_skill() -> dict:
    """Write the real copy, link every detected AI, refresh recorded links/copies."""
    text = render_skill()
    _write_real_copy(text)
    data = state.load()
    targets: Dict[Path, str] = {}
    for name, (config, skills) in linked_agents().items():
        if config.is_dir():
            targets[skills] = name
    for rec in data["skill"]["links"]:
        parent = Path(rec["path"]).parent
        if parent.is_dir():
            targets.setdefault(parent, rec.get("agent", "custom"))
    links, not_linked = [], []
    for skills, agent in targets.items():
        target = skills / SKILL_NAME
        kind, reason = _link_into(skills, text)
        if kind:
            links.append({"agent": agent, "path": str(target), "kind": kind})
        else:
            not_linked.append({"agent": agent, "path": str(target), "reason": reason})
    data["skill"]["links"] = links
    state.save(data)
    return {**skill_status(), "not_linked": not_linked, "removed_old_copies": _remove_native_old_copies()}


def skill_status() -> dict:
    real = skill_dir()
    recorded = state.load()["skill"]["links"]
    links = [r for r in recorded
             if _links_to_real(Path(r["path"])) or (r["kind"] == "copy" and _is_our_copy(Path(r["path"])))]
    installed = (real / "SKILL.md").is_file()
    agents = []
    if installed:
        agents = [name for name, (config, _) in native_agents().items() if config.is_dir()]
        agents += [r["agent"] for r in links if r["agent"] not in agents and r["agent"] != "custom"]
    return {"path": str(real / "SKILL.md"), "installed": installed, "agents": agents,
            "links": [r["path"] for r in links if r["kind"] == "link"],
            "copies": [r["path"] for r in links if r["kind"] == "copy"]}


def link_skill(skills_dir: str) -> dict:
    """Link the skill into the skills folder of an AI that is not in the table."""
    target_dir = Path(skills_dir).expanduser()
    if not target_dir.is_absolute():
        target_dir = Path.cwd() / target_dir
    if target_dir.name == SKILL_NAME:
        raise ReachError(BAD_INPUT, f"give the skills folder, not the {SKILL_NAME} folder inside it",
                         hint=f"agent-reach skill link {target_dir.parent}")
    if os.path.realpath(target_dir) == os.path.realpath(skill_dir().parent):
        return skill_status()
    text = render_skill()
    if not (skill_dir() / "SKILL.md").is_file():
        _write_real_copy(text)
    kind, reason = _link_into(target_dir, text)
    if kind is None:
        raise ReachError(BAD_INPUT, f"{target_dir / SKILL_NAME}: {reason}; left it untouched",
                         hint="Ask the user to move it away, then run this again.")
    data = state.load()
    path = str(target_dir / SKILL_NAME)
    data["skill"]["links"] = [r for r in data["skill"]["links"] if r["path"] != path]
    data["skill"]["links"].append({"agent": _agent_for(target_dir), "path": path, "kind": kind})
    state.save(data)
    return skill_status()


def _skill_uninstall_targets() -> List[Path]:
    """Real copy, recorded links/copies, and our links/old copies in every known skills folder."""
    found: List[Path] = []
    for rec in state.load()["skill"]["links"]:
        p = Path(rec["path"])
        if _links_to_real(p) or _is_our_copy(p):
            found.append(p)
    known = [skills for _, skills in linked_agents().values()] + [skills for _, skills in native_agents().values()]
    for skills in known:
        p = skills / SKILL_NAME
        if _links_to_real(p) or _is_our_copy(p):
            found.append(p)
    real = skill_dir()
    if real.exists() or real.is_symlink():
        found.append(real)
    return list(dict.fromkeys(found))


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
    defaults = {c.name for c in _channels() if c.level == "default"}
    data = state.load()
    data["migrated_from"] = "pre-2.0"
    state.save(data)
    return {
        "migrated": True,
        "kept": "~/.agent-reach/config.yaml (keys and cookies unchanged)",
        "suggested_channels": sorted(set(hints) - defaults),
        "note": "Your own global tools were not removed. Old logins can be copied with `agent-reach login <channel> --import-existing`.",
    }


def setup() -> dict:
    migration = migrate() if not state.exists() and (state.root() / "config.yaml").exists() else None
    if not state.exists():
        state.save(state.load())
    skill = place_skill()
    defaults = [c for c in _channels() if c.level == "default"]
    added = []
    for ch in defaults:
        try:
            out = add(ch.name)
            added.append({"channel": ch.name, "ok": True, "tools": out["tools"]})
        except ReachError as err:
            added.append({"channel": ch.name, "ok": False, "tools": [],
                          "error": {"code": err.code, "message": err.message, "hint": err.hint}})
    needed = list(dict.fromkeys(p for ch in defaults for p in ch.prereqs))
    prereqs = {}
    for p in needed:
        ok = PREREQS[p]["check"]()
        prereqs[p] = {"ok": ok, **({} if ok else {"hint": PREREQS[p]["hint"]})}
    optional = [
        {"channel": c.name, "level": c.level, "add": f"agent-reach add {c.name}",
         "needs": list(c.prereqs) + (["login"] if (c.login_url or c.login_argv) else [])
                  + ([c.needs_key] if c.needs_key else [])}
        for c in _channels() if c.level != "default"
    ]
    return {
        "version": __version__,
        "default_channels": added,
        "prerequisites": prereqs,
        "skill": skill,
        "optional_channels": optional,
        "logins": [{"channel": c.name, "command": f"agent-reach login {c.name}"} for c in defaults if _has_login(c)],
        "migration": migration,
    }


# ── update ──

def _version_tuple(v: str) -> tuple:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except ValueError:
        return ()


def update_check() -> dict:
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"User-Agent": "agent-reach", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            rel = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        raise ReachError(UPSTREAM_BROKEN, f"could not reach GitHub: {exc}") from None
    latest = str(rel.get("tag_name", "")).lstrip("v")
    return {
        "current": __version__,
        "latest": latest,
        "update_available": _version_tuple(latest) > _version_tuple(__version__),
        "notes": (rel.get("body") or "")[:2000],
    }


def install_method() -> str:
    """How this copy of Agent Reach was installed: uv | editable | other."""
    try:
        from importlib.metadata import distribution

        direct = distribution("agent-reach").read_text("direct_url.json") or "{}"
        if json.loads(direct).get("dir_info", {}).get("editable"):
            return "editable"
    except Exception:  # noqa: BLE001
        pass
    if (Path(sys.prefix) / "uv-receipt.toml").is_file():
        return "uv"
    return "other"


def _source(version: str) -> str:
    return f"https://github.com/{REPO}/archive/refs/tags/v{version}.zip"


def upgrade_command(version: str) -> List[str]:
    return ["uv", "tool", "install", "--force", _source(version)]


UNINSTALL_PROGRAM = "uv tool uninstall agent-reach"


def sync() -> dict:
    """After the program itself changed: bring tools to this version's pins, refresh the skill."""
    migration = migrate() if not state.exists() else None
    data = state.load()
    synced, problems = [], []
    for ch in _channels():
        if not is_added(ch, data):
            continue
        for t in ch.tools:
            try:
                synced.append(tools.ensure(t))
            except ReachError as err:
                problems.append({"tool": t, "code": err.code, "message": err.message, "hint": err.hint})
        ch.on_add()
    return {"version": __version__, "tools": synced, "problems": problems,
            "skill": place_skill(), "migration": migration}


def update(check_only: bool = False) -> dict:
    info = update_check()
    if check_only:
        return info
    method = install_method()
    if info["update_available"] and method != "editable":
        cmd = upgrade_command(info["latest"])
        if method != "uv":
            raise ReachError(
                NEED_SETUP, "this copy of Agent Reach was not installed with uv, so it cannot update itself",
                hint=f"Reinstall once with uv: `{' '.join(cmd)}`, then remove the old copy "
                     "(e.g. `pipx uninstall agent-reach` or `pip uninstall agent-reach`).",
            )
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        except FileNotFoundError:
            raise ReachError(NEED_SETUP, "uv is not on PATH", hint=PREREQS["uv"]["hint"]) from None
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

    root = state.root()
    targets = _skill_uninstall_targets()  # before state.json goes: it records the links
    targets += [root / n for n in _OWNED]
    targets += [tools.tool_dir(n) for n in tools.TOOLS] + [root / "tools" / "xiaoyuzhou"]
    targets = [t for t in targets if t.exists() or t.is_symlink()]
    globals_ = tools.uninstall_global_owned(dry_run=True)
    if not dry_run:
        browser.stop()
        tools.uninstall_global_owned(dry_run=False)
        for t in targets:
            _remove(t)
        for d in (root / "tools", root):
            try:
                d.rmdir()
            except OSError:
                pass
    removing = {str(t) for t in targets} | {str(root / "tools")}
    kept = sorted(str(p) for p in root.iterdir() if str(p) not in removing) if root.exists() else []
    return {"dry_run": dry_run, "removed": [str(t) for t in targets], "global_tools_removed": globals_,
            "kept_unrecognized": kept, "remove_program": UNINSTALL_PROGRAM}


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
