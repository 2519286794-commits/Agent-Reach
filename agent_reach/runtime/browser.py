"""The Agent Reach dedicated browser.

A separate Chrome whose profile lives in ~/.agent-reach/browser/profile/, so
every browser login Agent Reach relies on stays under ~/.agent-reach/. The user
installs the OpenCLI extension in it once; `agent-reach browser setup` then
records which OpenCLI profile it is (~/.agent-reach/browser/state.json).
The user's own ~/.opencli settings are never modified.

Browser channels open it on demand (`ensure_running`). Every Agent Reach use
touches ~/.agent-reach/browser/last_used; when Agent Reach launches the
browser it also starts one detached watcher (runtime.browser_watcher) that
closes the browser after IDLE_LIMIT seconds without use and exits when the
browser is gone.

Debugging is bound to 127.0.0.1:9222 only. Any local process that can reach
that port can control this browser; that is why it closes when idle.
"""

from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Iterator, List, Optional

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

#: Close the browser after this many seconds without Agent Reach use.
IDLE_LIMIT = 600.0
#: Longest wait for a cold start (measured ~42 s to OpenCLI connect on a Mac).
START_WAIT = 90.0
#: Extra wait for a browser that has been up longer than START_WAIT.
_RUNNING_GRACE = 5.0
_LOCK_WAIT = START_WAIT + 30.0


def browser_root() -> Path:
    return home_dir() / ".agent-reach" / "browser"


def profile_dir() -> Path:
    return browser_root() / "profile"


def _state_path() -> Path:
    return browser_root() / "state.json"


def _last_used_path() -> Path:
    return browser_root() / "last_used"


def _start_lock_path() -> Path:
    return browser_root() / "start.lock"


def watcher_lock_path() -> Path:
    return browser_root() / "watcher.lock"


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


# ── last use ──


def touch() -> None:
    """Record an Agent Reach use of the browser (resets the idle timer)."""
    make_private_dir(browser_root())
    path = _last_used_path()
    if not path.exists():
        atomic_write_private_text(path, "")
    os.utime(path)


def last_used() -> Optional[float]:
    try:
        return _last_used_path().stat().st_mtime
    except OSError:
        return None


# ── cross-process locks ──


def _open_lock(path: Path) -> int:
    make_private_dir(path.parent)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    return os.open(path, flags, 0o600)


def try_lock(fd: int) -> bool:
    """Take an exclusive lock on `fd` without blocking."""
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


@contextlib.contextmanager
def _locked(path: Path, wait: float) -> Iterator[None]:
    """Hold an exclusive lock on `path`; ReachError after `wait` seconds."""
    fd = _open_lock(path)
    try:
        deadline = time.monotonic() + wait
        while not try_lock(fd):
            if time.monotonic() >= deadline:
                from .result import UPSTREAM_BROKEN, ReachError

                raise ReachError(UPSTREAM_BROKEN, "another Agent Reach process is still starting the browser")
            time.sleep(0.2)
        yield
    finally:
        os.close(fd)  # closing releases the lock


def start_lock(wait: float = _LOCK_WAIT):
    """Serializes launching (and idle-closing) the browser across processes."""
    return _locked(_start_lock_path(), wait)


def watcher_running() -> bool:
    fd = _open_lock(watcher_lock_path())
    try:
        return not try_lock(fd)
    finally:
        os.close(fd)


# ── process ──


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


def _launch(url: str) -> None:
    """Start Chrome on the dedicated profile, then the idle watcher. Caller holds start_lock()."""
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
    state = _load_state()
    state["started_at"] = time.time()
    _save_state(state)
    if not wait_for(is_running, START_WAIT):
        from .result import UPSTREAM_BROKEN, ReachError

        raise ReachError(UPSTREAM_BROKEN, f"the Agent Reach browser did not open within {START_WAIT:.0f}s")
    _spawn_watcher()


def _spawn_watcher() -> None:
    """Start the detached idle watcher unless one is already running."""
    if watcher_running():
        return
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(
        [sys.executable, "-m", "agent_reach.runtime.browser_watcher"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )
    # Hold start_lock until the watcher owns its lock, so a racing launch sees it.
    wait_for(watcher_running, 5.0, interval=0.1)


def wait_for(check: Callable[[], bool], seconds: float, interval: float = 1.0) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        if check():
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(interval)


def _remaining_start_wait() -> float:
    """How long a browser that is open but not ready yet still gets."""
    started = _load_state().get("started_at") or 0.0
    return max(_RUNNING_GRACE, started + START_WAIT - time.time())


def start(url: str = "about:blank") -> None:
    """Show `url` in the dedicated browser, launching it if needed (login, setup)."""
    touch()
    if is_running():
        open_url(url)
        return
    with start_lock():
        if is_running():
            open_url(url)
            return
        _launch(url)


def ensure_running(context: Optional[str] = None) -> None:
    """Make the dedicated browser ready for an action, launching it if needed.

    With `context`, also wait until that OpenCLI profile is connected.
    The wait does not count against the action's --timeout.
    Raises ReachError when it is not ready within START_WAIT.
    """
    from .clock import off_the_clock
    from .result import NEED_SETUP, UPSTREAM_BROKEN, ReachError

    touch()

    def ready() -> bool:
        return is_running() and (context is None or context in connected_contexts())

    if ready():
        return
    with off_the_clock(), start_lock():
        if not is_running():
            _launch("about:blank")
        if not wait_for(ready, _remaining_start_wait()):
            if not is_running():
                raise ReachError(UPSTREAM_BROKEN, "the Agent Reach browser closed while starting")
            raise ReachError(
                NEED_SETUP, "the Agent Reach browser is running but OpenCLI is not connected to it",
                hint="Ask the user to check the OpenCLI extension is enabled in the Agent Reach browser window.",
            )
    touch()


def stop(timeout: float = 10.0) -> bool:
    """Close the dedicated browser: CDP Browser.close, then terminate. True if it is closed."""
    if not is_running():
        return True
    from . import cdp

    info = cdp.call("SystemInfo.getProcessInfo") or {}
    pid = next((p.get("id") for p in info.get("processInfo", []) if p.get("type") == "browser"), None)
    cdp.call("Browser.close")
    if wait_for(lambda: not is_running(), timeout, interval=0.2):
        return True
    if pid:
        import signal

        with contextlib.suppress(OSError):
            os.kill(int(pid), signal.SIGTERM)
    return wait_for(lambda: not is_running(), 5.0, interval=0.2)


def open_url(url: str) -> None:
    """Open a new tab in the running dedicated browser."""
    req = urllib.request.Request(f"{CDP_URL}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    with urllib.request.urlopen(req, timeout=5):
        pass


# ── OpenCLI binding ──


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
        "idle_close_after_s": int(IDLE_LIMIT),
    }


def setup_problems() -> List[str]:
    """What blocks browser-login channels right now (offline checks only)."""
    if not bound_context():
        return ["Agent Reach browser not set up: run `agent-reach browser setup`"]
    return []
