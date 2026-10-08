# -*- coding: utf-8 -*-
"""Twitter/X — check if twitter-cli or bird CLI is available."""

import os
import shutil

from agent_reach.backends.opencli import opencli_call, opencli_items
from agent_reach.runtime.result import UPSTREAM_BROKEN, ReachError
from agent_reach.utils.url import host_matches

from .base import Action, Channel, Param

_TWITTER_LOGIN_HINT = (
    "Ask the user to log in to x.com in their own Chrome (the one with the "
    "OpenCLI extension). Never log in or read browser cookies for them."
)


def _x(args, timeout: float) -> list:
    items = opencli_items(opencli_call("twitter", list(args), timeout=timeout, login_hint=_TWITTER_LOGIN_HINT))
    if not items:
        raise ReachError(UPSTREAM_BROKEN, "OpenCLI returned nothing; the page most likely did not load")
    return items


def twitter_cli_child_env(config=None) -> dict[str, str]:
    """Return saved credentials missing from the current process environment.

    The returned mapping is meant for a single child process.  Existing shell
    variables remain authoritative and ``os.environ`` is never mutated.
    """
    if config is None:
        return {}

    child_env = {}
    for env_name, config_key in (
        ("TWITTER_AUTH_TOKEN", "twitter_auth_token"),
        ("TWITTER_CT0", "twitter_ct0"),
    ):
        if env_name in os.environ:
            continue
        value = config.get(config_key)
        if value:
            child_env[env_name] = str(value)
    return child_env


class TwitterChannel(Channel):
    name = "twitter"
    description = "Twitter/X 推文"
    backends = ["twitter-cli", "OpenCLI", "bird CLI (legacy)"]
    tier = 1

    # twitter-cli is not used here: even with explicit credentials it re-reads
    # browser cookies whenever verification fails.
    level = "experimental"
    login_url = "https://x.com/i/flow/login"
    tools = ("opencli",)
    prereqs = ("node", "chrome")

    def setup_problems(self):
        from agent_reach.runtime.browser import setup_problems

        return setup_problems()

    actions = (
        Action(
            "search",
            "Search tweets",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("opencli", "_opencli_search"),),
            live_test={"query": "openai", "limit": 2},
        ),
        Action(
            "profile",
            "A user's profile",
            (Param("username", "handle without @"),),
            (("opencli", "_opencli_profile"),),
            live_test={"username": "OpenAI"},
        ),
        Action(
            "tweets",
            "A user's recent tweets",
            (
                Param("username", "handle without @"),
                Param("limit", "max tweets", required=False, type=int, default=5),
            ),
            (("opencli", "_opencli_tweets"),),
        ),
        Action(
            "thread",
            "A tweet with its replies",
            (Param("target", "tweet id or link"),),
            (("opencli", "_opencli_thread"),),
        ),
    )

    def can_handle(self, url: str) -> bool:
        return host_matches(url, "x.com", "twitter.com")

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins.

        与其他多后端渠道同一套两段式：先收集全部候选状态，第一个 ok 获胜；
        没有 ok 才轮到第一个 warn——否则「装了但未登录」的 twitter-cli
        会把排在后面、完整可用的 OpenCLI 挡在门外。
        """
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "twitter-cli":
                result = self._check_twitter_cli(config)
            elif backend == "OpenCLI":
                result = self._check_opencli()
            elif backend == "bird CLI (legacy)":
                result = self._check_bird()
            else:
                continue

            if result is None:
                continue  # 未安装——不参与候选
            findings.append((backend, *result))

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend if status == "ok" else None
                    return status, message

        if findings:  # 只剩 broken/timeout 候选
            return "error", "\n".join(m for _, _, m in findings)

        return "warn", (
            "Twitter CLI 未安装。安装方式：\n"
            "  pipx install twitter-cli\n"
            "或：\n"
            "  uv tool install twitter-cli"
        )

    def _check_twitter_cli(self, config=None):
        """Inspect explicit credentials without starting twitter-cli.

        Upstream ``twitter status`` automatically reads browser cookies when
        credentials are missing *or invalid*. Doctor cannot disable that
        fallback, so executing it would violate the Cookie-Editor-only policy.
        """
        if not shutil.which("twitter"):
            return None

        child_env = twitter_cli_child_env(config)
        auth_token = os.environ.get("TWITTER_AUTH_TOKEN") or child_env.get(
            "TWITTER_AUTH_TOKEN"
        )
        ct0 = os.environ.get("TWITTER_CT0") or child_env.get("TWITTER_CT0")
        if auth_token and ct0:
            return "warn", (
                "twitter-cli 已安装，且 Cookie-Editor 凭据已配置；"
                "Doctor 不会执行 `twitter status`，因为上游在验证失败时会"
                "自动读取浏览器 Cookie。请在你明确同意时手动验证。"
            )
        return "warn", (
            "twitter-cli 已安装但没有完整的显式凭据。请用 Cookie-Editor "
            "从 x.com 导出后运行：\n"
            "  agent-reach configure twitter-cookies\n"
            "Doctor 不会自动读取浏览器 Cookie。"
        )

    def _check_opencli(self):
        """OpenCLI candidate. None = not installed."""
        from agent_reach.backends import opencli_status

        st = opencli_status()
        if not st.installed:
            return None
        if st.broken:
            return "error", st.hint
        if st.ready:
            return "warn", (
                "OpenCLI 桥接已连接，但 Twitter/X 登录态和实际命令未实时验证；"
                "Doctor 不执行平台命令，因此当前不标记为可用。"
            )
        return "warn", st.hint

    def _check_bird(self):
        """Inspect legacy bird credentials without launching browser fallback."""
        for cmd in ("bird", "birdx"):
            if not shutil.which(cmd):
                continue
            if os.environ.get("AUTH_TOKEN") and os.environ.get("CT0"):
                return (
                    "warn",
                    f"{cmd} 已安装且显式环境凭据存在；Doctor 为避免上游"
                    "浏览器 Cookie 回退，不执行 `check`，未实时验证。",
                )
            return "warn", (
                f"{cmd} 已安装但未检测到显式 AUTH_TOKEN/CT0；"
                "仅使用 Cookie-Editor 手动导出的凭据。"
            )
        return None

    # ── unified entry backends ──

    def _opencli_search(self, *, query: str, limit: int, timeout: float) -> list:
        return _x(["search", query, "--limit", str(limit)], timeout)[:limit]

    def _opencli_profile(self, *, username: str, timeout: float) -> list:
        return _x(["profile", username.lstrip("@")], timeout)[:1]

    def _opencli_tweets(self, *, username: str, limit: int, timeout: float) -> list:
        return _x(["tweets", username.lstrip("@"), "--limit", str(limit)], timeout)[:limit]

    def _opencli_thread(self, *, target: str, timeout: float) -> list:
        tweet_id = str(target).rstrip("/").split("/")[-1].split("?")[0]
        return _x(["thread", tweet_id], timeout)
