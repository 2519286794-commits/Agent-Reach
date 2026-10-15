"""Idle watcher for the Agent Reach browser (`python -m agent_reach.runtime.browser_watcher`).

Started detached by runtime.browser when Agent Reach launches the browser.
Holds ~/.agent-reach/browser/watcher.lock so only one runs; exits when the
browser is gone, and closes it after `idle` seconds without Agent Reach use.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import time
from typing import Optional

from . import browser


def watch(idle: Optional[float] = None, poll: float = 15.0) -> str:
    """Run until the browser is gone. Returns why it stopped."""
    idle = browser.IDLE_LIMIT if idle is None else idle
    fd = browser._open_lock(browser.watcher_lock_path())
    try:
        # A probe (watcher_running) holds the lock for an instant; a live watcher holds it for good.
        if not browser.wait_for(lambda: browser.try_lock(fd), 2.0, interval=0.1):
            return "another watcher is running"
        began = time.time()
        while True:
            if not browser.is_running():
                return "browser closed"
            used = max(began, browser.last_used() or 0.0)
            left = used + idle - time.time()
            if left <= 0:
                with contextlib.suppress(Exception), browser.start_lock(wait=5.0):
                    used = max(began, browser.last_used() or 0.0)
                    if used + idle <= time.time() and browser.stop():
                        return "closed after idle"
                left = poll  # used again meanwhile, or close failed: check later
            time.sleep(min(poll, left + 0.5))
    finally:
        os.close(fd)


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent_reach.runtime.browser_watcher")
    parser.add_argument("--idle", type=float, default=None, help="seconds without use before closing")
    ns = parser.parse_args()
    watch(ns.idle)


if __name__ == "__main__":
    main()
