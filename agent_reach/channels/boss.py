# -*- coding: utf-8 -*-
"""Boss直聘 — boss-agent-cli drives the Agent Reach browser over CDP (127.0.0.1:9222).

headless is off-limits (triggers code 36 risk control), so search runs against
the Agent Reach browser with the user's own login (opened on demand).

Two login stores, both required:
- the session under ~/.agent-reach/sessions/boss-agent-cli/ (`boss login --cdp`
  writes it; boss-agent-cli refuses to start without it);
- the browser cookies in the Agent Reach browser profile, which the search
  actually sends.
"""

import json

from agent_reach.runtime.result import (
    NEED_LOGIN,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
)
from agent_reach.runtime.run import CommandFailed, run_cmd
from agent_reach.runtime.sessions import session_env
from agent_reach.utils.url import host_matches

from .base import Action, Channel, Param

_CDP_URL = "http://localhost:9222"


class BossChannel(Channel):
    name = "boss"
    description = "Boss直聘 职位搜索与 JD"
    level = "optional"
    login_url = "https://www.zhipin.com/web/user/?ka=header-login"
    session = "boss-agent-cli"
    login_argv = ("boss", "--cdp-url", "http://localhost:9222", "login", "--cdp")
    legacy_state = (".boss-agent",)
    tools = ("boss-agent-cli",)
    prereqs = ("chrome",)
    actions = (
        Action(
            "search",
            "Search jobs (needs the dedicated Chrome with a zhipin.com login)",
            (
                Param("query", "job keywords"),
                Param("city", "city, e.g. 深圳", required=False),
                Param("limit", "max results", required=False, type=int, default=10),
            ),
            (("boss-agent-cli", "_cli_search"),),
            live_test={"query": "Python", "city": "深圳", "limit": 3},
            timeout=90,
        ),
    )

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "zhipin.com")

    # ── unified entry backends ──

    def _cli_search(self, *, query: str, city, limit: int, timeout: float) -> list:
        from agent_reach.runtime import browser

        if not (browser.is_running() or browser.profile_dir().is_dir()):
            # boss needs no extension, only a zhipin.com login in the browser, which a never-opened one lacks.
            raise ReachError(
                NEED_LOGIN,
                "nobody has logged in to zhipin.com in the Agent Reach browser yet",
                hint="Run `agent-reach login boss`, let the user log in to zhipin.com in that window, then run `agent-reach login boss --sync`.",
            )
        browser.ensure_running()
        args = ["boss", "--json", "--browser-source", "existing-browser", "--cdp-url", _CDP_URL, "search", query]
        if city:
            args += ["--city", city]
        try:
            out = run_cmd(args, timeout=timeout, env=session_env("boss-agent-cli"))
        except CommandFailed as exc:
            out = exc.stdout
            if "{" not in out:
                raise
        try:
            payload = json.loads(out[out.index("{"):])
        except ValueError:
            raise ReachError(UPSTREAM_BROKEN, "boss-agent-cli returned unreadable output") from None
        if not payload.get("ok"):
            err = payload.get("error") or {}
            code = str(err.get("code", "")).upper()
            message = str(err.get("message", "boss-agent-cli failed"))[:300]
            if "AUTH" in code or "LOGIN" in code:
                raise ReachError(
                    NEED_LOGIN, message,
                    hint="Ask the user to log in to zhipin.com in the dedicated Chrome window, then run `boss --cdp-url http://localhost:9222 login --cdp`.",
                )
            raise ReachError(UPSTREAM_BROKEN, message)
        data = payload.get("data")
        rows = data if isinstance(data, list) else ((data or {}).get("items") or (data or {}).get("jobs") or [])
        items = []
        for r in rows[:limit]:
            if not isinstance(r, dict):
                continue
            job_id = r.get("job_id")
            items.append(
                make_item(
                    title=r.get("title"),
                    url=f"https://www.zhipin.com/job_detail/{job_id}.html" if job_id else None,
                    author=r.get("company"),
                    text=" · ".join(str(x) for x in (r.get("salary"), r.get("city"), r.get("experience"), r.get("education")) if x),
                    raw=r,
                )
            )
        return items
