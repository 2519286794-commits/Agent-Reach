"""The Agent Reach dedicated browser.

A separate Chrome whose profile lives in ~/.agent-reach/browser/profile/, so
every browser login Agent Reach relies on stays under ~/.agent-reach/. The user
installs the OpenCLI extension in it once; `agent-reach browser setup` then
records which OpenCLI profile it is (~/.agent-reach/browser/state.json).
The user's own ~/.opencli settings are never modified.

Debugging is bound to 127.0.0.1:9222 only. Any local process that can reach
that port can control this browser; close it when not in use.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import socket
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import List, Optional

from agent_reach.utils.paths import (
    PrivatePathError,
    atomic_write_private_text,
    home_dir,
    make_private_dir,
    read_small_text_no_follow,
)

CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"
_CONTEXT_RE = re.compile(r"^\s*(\S+)\s+[—-]\s+connected\b", re.M)


def browser_root() -> Path:
    return home_dir() / ".agent-reach" / "browser"


def profile_dir() -> Path:
    return browser_root() / "profile"


def _state_path() -> Path:
    return browser_root() / "state.json"


def _load_state() -> dict:
    try:
        text = read_small_text_no_follow(_state_path(), max_bytes=64 * 1024)
    except (OSError, PrivatePathError):
        return {}
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {}


def _save_state(state: dict) -> None:
    make_private_dir(browser_root())
    atomic_write_private_text(_state_path(), json.dumps(state, indent=2))


def chrome_binary() -> Optional[str]:
    system = platform.system()
    candidates = []
    if system == "Darwin":
        candidates = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    elif system == "Windows":
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
    else:
        candidates = [shutil.which(n) for n in ("google-chrome", "google-chrome-stable", "chromium")]
    return next((c for c in candidates if c and os.path.exists(c)), None)


def is_running() -> bool:
    with socket.socket() as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", CDP_PORT)) == 0


def start(url: str = "about:blank") -> None:
    """Launch the dedicated browser if it is not running; otherwise open `url` in it."""
    if is_running():
        open_url(url)
        return
    exe = chrome_binary()
    if not exe:
        from .result import NEED_SETUP, ReachError

        raise ReachError(NEED_SETUP, "Google Chrome is not installed", hint="Ask the user to install Google Chrome.")
    make_private_dir(profile_dir())
    subprocess.Popen(
        [
            exe,
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={CDP_PORT}",
            f"--user-data-dir={profile_dir()}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=(os.name != "nt"),
    )


def open_url(url: str) -> None:
    """Open a new tab in the running dedicated browser."""
    req = urllib.request.Request(f"{CDP_URL}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    with urllib.request.urlopen(req, timeout=5):
        pass


def connected_contexts() -> List[str]:
    """OpenCLI Browser Bridge profiles connected right now."""
    from .run import run_cmd

    out = run_cmd(["opencli", "profile", "list"], timeout=20)
    return _CONTEXT_RE.findall(out)


def bound_context() -> Optional[str]:
    """The OpenCLI profile recorded as the dedicated browser, or None."""
    return _load_state().get("opencli_context") or None


def bind() -> dict:
    """Record which OpenCLI profile is the dedicated browser.

    The first call snapshots profiles already connected (the user's own
    Chrome). After the user installs the extension in the dedicated window,
    the next call finds exactly one new profile and records it.
    """
    state = _load_state()
    now = connected_contexts()
    if state.get("opencli_context") in now:
        return {"status": "ready", "context": state["opencli_context"]}
    if "baseline" not in state:
        state["baseline"] = now
        _save_state(state)
    new = [c for c in now if c not in state["baseline"]]
    if len(new) == 1:
        state["opencli_context"] = new[0]
        _save_state(state)
        return {"status": "ready", "context": new[0]}
    if len(new) > 1:
        return {"status": "ambiguous", "candidates": new}
    return {"status": "waiting_for_extension"}


def status() -> dict:
    ctx = bound_context()
    running = is_running()
    connected = None
    if ctx and running:
        try:
            connected = ctx in connected_contexts()
        except Exception:  # noqa: BLE001 - status must never raise
            connected = False
    return {
        "profile_dir": str(profile_dir()),
        "running": running,
        "opencli_context": ctx,
        "opencli_connected": connected,
    }
