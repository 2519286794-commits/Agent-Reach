"""Shared owned-browser environment and cross-process action locks."""

import hashlib
import sys
from contextlib import contextmanager

from .result import NEED_SETUP, ReachError


def profile_for(channel: str):
    """All browser channels use the same Reach-owned destination profile."""
    return "dedicated"






def setup_problems(channel: str):
    return []  # add/first use prepare and reopen the owned browser automatically


def environment(channel: str):
    from . import browser
    browser.ensure_running()
    profile = browser.bound_context()
    if not profile:
        raise ReachError(NEED_SETUP, "OpenCLI has not connected to the dedicated browser")
    browser.touch()
    return {"OPENCLI_PROFILE": profile, "OPENCLI_WINDOW": "background",
            "OPENCLI_CDP_ENDPOINT": "", "OPENCLI_CDP_TARGET": ""}


# ponytail: one nonblocking OS file lock per profile; callers retry BUSY later.
# No daemon, queue, stale-lock cleanup, or guessed browser ownership.


@contextmanager
def execution_lock(profile: str):
    from agent_reach.utils.paths import ensure_no_symlink_path, make_private_dir

    from . import state

    folder = state.root() / "browser-locks"
    make_private_dir(folder)
    path = folder / (hashlib.sha256(profile.encode()).hexdigest() + ".lock")
    ensure_no_symlink_path(path, "browser lock")
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ReachError("BUSY", "Another Reach command is using this Chrome profile") from None
        try:
            yield
        finally:
            if sys.platform == "win32":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
