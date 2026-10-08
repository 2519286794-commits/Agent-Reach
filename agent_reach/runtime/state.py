"""~/.agent-reach/state.json: which channels are added, which tools we installed, last checks.

    {
      "version": 1,
      "channels": {"bilibili": {"added_at": "..."}},
      "tools": {"bili-cli": {"spec": "...", "owner": "agent-reach" | "user", "scope": "private" | "global"}},
      "checks": {"bilibili": {"at": "...", "actions": {"search": true}}}
    }

`owner` decides what uninstall may delete: only "agent-reach" entries.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from agent_reach.utils.paths import (
    PrivatePathError,
    atomic_write_private_text,
    home_dir,
    make_private_dir,
    read_small_text_no_follow,
)

STATE_VERSION = 1


def root() -> Path:
    return home_dir() / ".agent-reach"


def state_path() -> Path:
    return root() / "state.json"


def exists() -> bool:
    return state_path().is_file()


def load() -> dict:
    try:
        text = read_small_text_no_follow(state_path(), max_bytes=1024 * 1024)
        data = json.loads(text) if text else {}
    except (OSError, ValueError, PrivatePathError):
        data = {}
    data.setdefault("version", STATE_VERSION)
    for key in ("channels", "tools", "checks"):
        data.setdefault(key, {})
    return data


def save(data: dict) -> None:
    make_private_dir(root())
    atomic_write_private_text(state_path(), json.dumps(data, indent=2, ensure_ascii=False))


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_seconds(iso: str) -> float:
    try:
        then = _dt.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return float("inf")
    return (_dt.datetime.now(_dt.timezone.utc) - then).total_seconds()
