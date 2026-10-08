"""Login state for upstream tools, kept under ~/.agent-reach/sessions/<tool>/.

Command-line tools store their login in the user's home directory. We run
each one with HOME pointed at its own session directory, so its login lives
under Agent Reach and nowhere else. Uninstall removes it with the rest of
~/.agent-reach/.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from agent_reach.utils.paths import ensure_no_symlink_path, home_dir, make_private_dir


def sessions_root() -> Path:
    return home_dir() / ".agent-reach" / "sessions"


def session_dir(tool: str) -> Path:
    """The tool's private home directory (created on first use)."""
    return make_private_dir(sessions_root() / tool)


def session_env(tool: str) -> dict:
    """Environment overrides that make `tool` store its login in session_dir()."""
    home = str(session_dir(tool))
    return {"HOME": home, "USERPROFILE": home}


def has_login_state(tool: str) -> bool:
    """Whether the tool has saved anything in its session directory."""
    root = sessions_root() / tool
    return root.is_dir() and any(p.is_file() for p in root.rglob("*"))


def clear_session(tool: str) -> bool:
    """Delete the tool's session directory. Returns whether anything was removed."""
    root = sessions_root() / tool
    if not root.exists():
        return False
    ensure_no_symlink_path(root, "登录目录")
    shutil.rmtree(root)
    return True


def import_legacy_state(tool: str, names) -> list:
    """Copy the tool's existing login from the real home into its session (explicit opt-in)."""
    copied = []
    target = session_dir(tool)
    for name in names:
        src = home_dir() / name
        if src.is_dir() and not src.is_symlink():
            shutil.copytree(src, target / name, dirs_exist_ok=True)
            copied.append(str(src))
    return copied
