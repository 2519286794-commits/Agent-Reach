"""Upstream tools Agent Reach installs, at pinned versions.

Two kinds:
- private: installed into ~/.agent-reach/tools/<name>/ (its own venv or npm
  prefix). Never on the user's PATH; the user's own copy, if any, is untouched.
- singleton: tools that can only exist once per machine (OpenCLI owns a fixed
  daemon port and a Chrome extension). If the user already has one that is new
  enough we use theirs; if it is too old we upgrade only with explicit consent;
  if it is missing we install it globally and record it as ours.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from . import state
from .result import NEED_SETUP, UPSTREAM_BROKEN, ReachError


@dataclass(frozen=True)
class Tool:
    name: str
    kind: str                 # "pip" | "npm"
    spec: str                 # pinned install spec
    commands: Tuple[str, ...]  # executables it provides
    singleton: bool = False
    min_version: str = ""     # singleton only: oldest user copy we accept


TOOLS = {
    t.name: t
    for t in (
        Tool("bili-cli", "pip", "bilibili-cli==0.6.2", ("bili",)),
        Tool(
            "boss-agent-cli", "pip",
            "boss-agent-cli @ git+https://github.com/can4hou6joeng4/boss-agent-cli.git"
            "@4c991b77086a203173bf08a4cb64a23af6514fe6",
            ("boss",),
        ),
        Tool("mcporter", "npm", "mcporter@0.14.2", ("mcporter",)),
        Tool("opencli", "npm", "@jackwener/opencli@1.8.6", ("opencli",), singleton=True, min_version="1.8.6"),
    )
}

#: Command name → tool, for resolving executables.
_BY_COMMAND = {c: t for t in TOOLS.values() for c in t.commands}


def tools_root() -> Path:
    return state.root() / "tools"


def tool_dir(name: str) -> Path:
    return tools_root() / name


def _private_bin(tool: Tool, command: str) -> Path:
    base = tool_dir(tool.name)
    if tool.kind == "pip":
        sub = "Scripts" if os.name == "nt" else "bin"
        return base / "venv" / sub / (command + (".exe" if os.name == "nt" else ""))
    return base / "node_modules" / ".bin" / (command + (".cmd" if os.name == "nt" else ""))


def resolve(command: str) -> Optional[str]:
    """Absolute path for `command`: our private copy first, then the user's PATH."""
    tool = _BY_COMMAND.get(command)
    if tool and not tool.singleton:
        private = _private_bin(tool, command)
        if private.exists():
            return str(private)
    return shutil.which(command)


def _version_tuple(text: str) -> tuple:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(x) for x in m.groups()) if m else ()


def installed_version(tool: Tool) -> Optional[str]:
    exe = resolve(tool.commands[0])
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"\d+\.\d+\.\d+", out.stdout + out.stderr)
    return m.group(0) if m else None


def _install_env() -> dict:
    """pip and npm only read proxy env vars; hand them the OS proxy (e.g. the macOS system proxy) when none is set."""
    env = dict(os.environ)
    if not (env.get("HTTPS_PROXY") or env.get("https_proxy")):
        import urllib.request

        found = urllib.request.getproxies()
        proxy = found.get("https") or found.get("http")
        if proxy:
            env["HTTPS_PROXY"] = env["HTTP_PROXY"] = proxy
    return env


def _run(argv, timeout: float = 600) -> None:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=_install_env())
    except FileNotFoundError:
        raise ReachError(NEED_SETUP, f"{Path(argv[0]).name} is not installed") from None
    except subprocess.TimeoutExpired:
        raise ReachError(UPSTREAM_BROKEN, f"installing timed out: {' '.join(argv[:3])}") from None
    if proc.returncode != 0:
        last = next((ln for ln in reversed(proc.stderr.splitlines()) if ln.strip()), "")
        raise ReachError(UPSTREAM_BROKEN, f"install failed: {last[:300]}")


def _install(tool: Tool, *, global_: bool = False) -> None:
    if tool.kind == "pip":
        venv = tool_dir(tool.name) / "venv"
        shutil.rmtree(venv, ignore_errors=True)
        venv.parent.mkdir(parents=True, exist_ok=True)
        _run([sys.executable, "-m", "venv", str(venv)])
        py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        _run([str(py), "-m", "pip", "install", "--quiet", "--disable-pip-version-check", tool.spec])
        return
    npm = shutil.which("npm")
    if not npm:
        raise ReachError(NEED_SETUP, "npm is not installed", hint="Ask the user to install Node.js (https://nodejs.org).")
    if global_:
        _run([npm, "install", "-g", tool.spec])
    else:
        prefix = tool_dir(tool.name)
        prefix.mkdir(parents=True, exist_ok=True)
        _run([npm, "install", "--prefix", str(prefix), "--no-fund", "--no-audit", tool.spec])


def ensure(name: str, *, allow_upgrade: bool = False) -> dict:
    """Make sure the tool is installed at an acceptable version; record it in state."""
    tool = TOOLS[name]
    data = state.load()
    entry = data["tools"].get(name)

    if tool.singleton:
        current = installed_version(tool)
        if current is None:
            _install(tool, global_=True)
            entry = {"spec": tool.spec, "owner": "agent-reach", "scope": "global"}
        elif _version_tuple(current) < _version_tuple(tool.min_version):
            if not allow_upgrade:
                raise ReachError(
                    NEED_SETUP,
                    f"{name} {current} is older than the required {tool.min_version}",
                    hint=f"Ask the user whether to upgrade their {name}; if yes, rerun with --allow-upgrade.",
                )
            _install(tool, global_=True)
            entry = {"spec": tool.spec, "owner": (entry or {}).get("owner", "user"), "scope": "global"}
        elif entry is None:
            entry = {"spec": f"user:{current}", "owner": "user", "scope": "global"}
    elif not entry or entry.get("spec") != tool.spec or not _private_bin(tool, tool.commands[0]).exists():
        _install(tool)
        entry = {"spec": tool.spec, "owner": "agent-reach", "scope": "private"}

    data["tools"][name] = entry
    state.save(data)
    return {"tool": name, **entry}


def remove_private(name: str) -> bool:
    """Delete a private install. Singletons are never removed here."""
    tool = TOOLS[name]
    if tool.singleton:
        return False
    data = state.load()
    removed = data["tools"].pop(name, None) is not None
    if tool_dir(name).exists():
        shutil.rmtree(tool_dir(name))
        removed = True
    state.save(data)
    return removed


def uninstall_global_owned(dry_run: bool) -> list:
    """Global singletons we installed (owner agent-reach); uninstall them."""
    out = []
    for name, entry in state.load()["tools"].items():
        tool = TOOLS.get(name)
        if tool and tool.singleton and entry.get("owner") == "agent-reach" and entry.get("scope") == "global":
            out.append(f"npm -g {tool.spec.rsplit('@', 1)[0]}")
            if not dry_run and shutil.which("npm"):
                subprocess.run([shutil.which("npm"), "uninstall", "-g", tool.spec.rsplit("@", 1)[0]],
                               capture_output=True, timeout=300)
    return out
