# -*- coding: utf-8 -*-
"""
Channel base class — platform availability checking.

Each channel represents a platform (YouTube, Twitter, GitHub, etc.)
and provides:
  - can_handle(url) → does this URL belong to this platform?
  - check(config) → is the upstream tool installed and configured?

After installation, agents call upstream tools directly.

Backend routing semantics:
  - `backends` is an ORDERED candidate list: backends[0] is the preferred
    backend, the rest are fallbacks. "Switching backends" for a platform
    means reordering this list (or a user override) — not rewriting code.
  - check() must set `self.active_backend` to the backend that is actually
    serving the channel right now (None when nothing usable is found).
    shutil.which() alone is NOT proof of health — a stale venv shim passes
    which() but cannot execute (see agent_reach.probe). Channels should
    really execute a lightweight command before claiming a backend active.
  - Users can force a backend with config key `<channel>_backend`
    (or env var `<CHANNEL>_BACKEND`); ordered_backends() applies it.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Param:
    """One argument of a unified action."""

    name: str
    help: str
    required: bool = True
    type: type = str
    default: object = None


@dataclass(frozen=True)
class Action:
    """A unified action (`agent-reach <channel> <action>`).

    `backends` is ordered: (backend label, channel method name). The
    dispatcher tries them in order and falls back on retryable errors.
    `live_test` holds params for `agent-reach check`; a backend passes when
    the call succeeds and returns at least one item.
    """

    name: str
    help: str
    params: Tuple[Param, ...]
    backends: Tuple[Tuple[str, str], ...]
    live_test: Optional[Dict[str, object]] = None
    #: Default timeout in seconds for slow actions (e.g. transcription); None = global default.
    timeout: Optional[float] = None


class Channel(ABC):
    """Base class for all channels."""

    name: str = ""                    # e.g. "youtube"
    description: str = ""             # e.g. "YouTube 视频和字幕"
    backends: List[str] = []          # ordered candidates — backends[0] = preferred
    tier: int = 0                     # 0=zero-config, 1=needs free key, 2=needs setup

    #: Unified-entry tier: "default" / "optional" / "experimental".
    #: Empty means the channel is not on the unified entry yet. `tier` above
    #: is the legacy doctor grouping and goes away at cutover.
    level: str = ""
    #: Unified actions this channel exposes.
    actions: Tuple[Action, ...] = ()
    #: Tool whose login lives in ~/.agent-reach/sessions/<session>/ ("" = none).
    session: str = ""
    #: Interactive command the user runs to log in (run with HOME = session dir).
    login_argv: Tuple[str, ...] = ()
    #: Directories under the real home where the tool used to keep its login,
    #: copied into the session only when the user asks (`login --import-existing`).
    legacy_state: Tuple[str, ...] = ()
    #: Page the user logs in on, opened in the Agent Reach browser by `agent-reach login`.
    login_url: str = ""
    #: Upstream tools (keys of runtime.tools.TOOLS) `agent-reach add` installs.
    tools: Tuple[str, ...] = ()
    #: Machine prerequisites we only check (keys of runtime.manage.PREREQS).
    prereqs: Tuple[str, ...] = ()
    #: Config keys `agent-reach logout` clears.
    logout_keys: Tuple[str, ...] = ()
    #: Run login_argv / tool calls with HOME = the session dir. False when the tool
    #: takes an explicit path instead (login_argv may use the `{session}` placeholder).
    session_home: bool = True

    def setup_problems(self) -> List[str]:
        """What still blocks this channel after its tools are installed (keys, browser...)."""
        return []

    def on_add(self) -> None:
        """Extra setup after tools are installed (e.g. register an MCP server)."""

    def on_remove(self) -> None:
        """Undo on_add."""

    def sync_login(self) -> Optional[dict]:
        """Pull login state from the Agent Reach browser after the user logged in there.

        Return a result dict, or None to fall back to running `login_argv`.
        """
        return None

    #: Backend currently serving this channel; set by check(), None = unavailable.
    active_backend: Optional[str] = None

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """Check if this channel can handle this URL."""
        ...

    def ordered_backends(self, config=None) -> List[str]:
        """Candidate backends in probe order, honoring the user override.

        The config key `<channel>_backend` (env `<CHANNEL>_BACKEND`) moves the
        named backend to the front of the list; unknown values are ignored so
        a stale override can never hide working backends.
        """
        candidates = list(self.backends)
        override = config.get(f"{self.name}_backend") if config else None
        if override:
            for i, b in enumerate(candidates):
                if b == override or b.startswith(override):
                    candidates.insert(0, candidates.pop(i))
                    break
        return candidates

    def check(self, config=None) -> Tuple[str, str]:
        """
        Check if this channel's upstream tool is available.
        Returns (status, message) where status is 'ok'/'warn'/'off'/'error'.

        Subclasses with external backends must really probe them (see
        agent_reach.probe.probe_command) and set self.active_backend.
        """
        self.active_backend = self.backends[0] if self.backends else "内置"
        return "ok", f"{'、'.join(self.backends) if self.backends else '内置'}"
