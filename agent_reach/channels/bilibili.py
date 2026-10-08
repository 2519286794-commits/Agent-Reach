# -*- coding: utf-8 -*-
"""Bilibili — multi-backend: bili-cli / OpenCLI / search API.

yt-dlp was REMOVED from this channel (live-verified 2026-06): bilibili's
risk control 412-blocks yt-dlp's requests in every configuration we
tried — latest version, direct, proxied, with warmed cookies — while
bili-cli keeps working (search/hot/video detail without login) and
OpenCLI covers subtitles through the browser session. yt-dlp remains the
YouTube backend; it just no longer serves bilibili.
"""

import json
import re
import urllib.request

from agent_reach.probe import probe_command
from agent_reach.runtime.result import (
    BAD_INPUT,
    NEED_LOGIN,
    NOT_FOUND,
    UPSTREAM_BROKEN,
    ReachError,
    make_item,
    unix_to_iso,
)
from agent_reach.runtime.run import CommandFailed, http_request, run_cmd
from agent_reach.runtime.sessions import session_env, sessions_root

from .base import Action, Channel, Param

_BV_RE = re.compile(r"BV[0-9A-Za-z]{10}")
_BILI_LOGIN_HINT = (
    "Bilibili subtitles need a login. Ask the user to run `bili login` and scan "
    "the QR code themselves; never log in on their behalf."
)


def _bvid(target: str, timeout: float) -> str:
    """BV id from a BV id, a video link, or a b23.tv short link."""
    t = str(target).strip()
    m = _BV_RE.search(t)
    if m:
        return m.group(0)
    if "b23.tv/" in t:
        url = t if "://" in t else f"https://{t}"
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            m = _BV_RE.search(resp.geturl())
        if m:
            return m.group(0)
    raise ReachError(BAD_INPUT, "target must be a BV id or a bilibili.com / b23.tv video link")


def _bili_json(args: list, timeout: float) -> dict:
    """Run bili-cli with --json; map its error envelope to unified codes."""
    try:
        out = run_cmd(["bili", *args, "--json"], timeout=timeout, env=session_env("bili-cli"))
    except CommandFailed as exc:
        out = exc.stdout
        if "{" not in out:
            raise
    try:
        payload = json.loads(out[out.index("{"):])
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, "bili-cli returned unreadable output") from None
    if not payload.get("ok"):
        err = payload.get("error") or {}
        code = str(err.get("code", ""))
        message = str(err.get("message", "bili-cli failed"))[:300]
        if code == "not_found":
            raise ReachError(NOT_FOUND, message)
        if "login" in code or "auth" in code or "credential" in code:
            raise ReachError(NEED_LOGIN, message, hint=_BILI_LOGIN_HINT)
        raise ReachError(UPSTREAM_BROKEN, message)
    return payload.get("data") or {}


def _cli_video_item(v: dict, text=None) -> dict:
    owner = v.get("owner") or {}
    return make_item(
        title=v.get("title"),
        url=v.get("url") or (f"https://www.bilibili.com/video/{v['bvid']}" if v.get("bvid") else None),
        author=owner.get("name") or v.get("author"),
        text=v.get("description") if text is None else text,
        raw=v,
    )


def _api_video_item(v: dict, text=None) -> dict:
    return make_item(
        title=v.get("title"),
        url=f"https://www.bilibili.com/video/{v.get('bvid')}" if v.get("bvid") else None,
        author=(v.get("owner") or {}).get("name"),
        published_at=unix_to_iso(v.get("pubdate")),
        text=v.get("desc") if text is None else text,
        raw={k: v.get(k) for k in ("bvid", "aid", "duration", "stat", "tname")},
    )


def _bili_api(path: str, timeout: float) -> dict:
    body = http_request(
        f"https://api.bilibili.com{path}",
        timeout=timeout,
        headers={"User-Agent": _UA, "Referer": "https://www.bilibili.com/"},
    )
    try:
        data = json.loads(body)
    except ValueError:
        raise ReachError(UPSTREAM_BROKEN, "Bilibili returned a verification page") from None
    if data.get("code") == -404:
        raise ReachError(NOT_FOUND, "video not found")
    if data.get("code") != 0:
        raise ReachError(UPSTREAM_BROKEN, f"Bilibili API code {data.get('code')}: {data.get('message')}")
    return data.get("data") or {}


_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
_TIMEOUT = 10
_SEARCH_API = "https://api.bilibili.com/x/web-interface/search/all/v2?keyword=test&page=1"


def _search_api_ok() -> bool:
    """Return True if Bilibili search API responds with code 0."""
    req = urllib.request.Request(_SEARCH_API, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read())
            return data.get("code") == 0
    except Exception:
        return False


class BilibiliChannel(Channel):
    name = "bilibili"
    description = "B站视频、字幕和搜索"
    backends = ["bili-cli", "OpenCLI", "B站搜索 API"]
    tier = 1

    level = "optional"
    session = "bili-cli"
    login_argv = ("bili", "login")
    legacy_state = (".bilibili-cli",)
    actions = (
        Action(
            "search",
            "Search videos",
            (
                Param("query", "what to search for"),
                Param("limit", "max results", required=False, type=int, default=5),
            ),
            (("bili-cli", "_cli_search"),),
            live_test={"query": "Python", "limit": 2},
        ),
        Action(
            "read",
            "Video title, uploader, description and stats",
            (Param("target", "BV id or video link"),),
            (("bili-cli", "_cli_read"), ("bilibili-api", "_api_read")),
            live_test={"target": "BV1GJ411x7h7"},
        ),
        Action(
            "hot",
            "Trending videos",
            (Param("limit", "max items", required=False, type=int, default=10),),
            (("bili-cli", "_cli_hot"), ("bilibili-api", "_api_hot")),
            live_test={"limit": 2},
        ),
        Action(
            "subtitle",
            "Full subtitle text of a video (needs a Bilibili login)",
            (Param("target", "BV id or video link"),),
            (("bili-cli", "_cli_subtitle"),),
            live_test={"target": "BV1GJ411x7h7"},
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "bilibili.com", "b23.tv")

    def check(self, config=None):
        """Probe candidates in order; first fully-usable backend wins."""
        self.active_backend = None
        findings = []

        for backend in self.ordered_backends(config):
            if backend == "bili-cli":
                result = self._check_bili_cli()
            elif backend == "OpenCLI":
                result = self._check_opencli()
            else:
                result = self._check_search_api()
            if result is None:
                continue
            findings.append((backend, *result))

        # 有后端断链时，即使别的候选兜底成功也要把处方带出来
        broken_notes = [m for _, s, m in findings if s == "error"]

        for wanted in ("ok", "warn"):
            for backend, status, message in findings:
                if status == wanted:
                    self.active_backend = backend if status == "ok" else None
                    if broken_notes:
                        message += "\n[备选后端异常] " + "；".join(broken_notes)
                    return status, message

        if findings:
            return "error", "\n".join(m for _, _, m in findings)

        return "off", (
            "没有可用的 B站后端（搜索 API 也不可达，可能是网络问题）。推荐：\n"
            "  pipx install bilibili-cli（搜索/热门/视频详情，无需登录）\n"
            "  或桌面装 OpenCLI（额外解锁字幕）：agent-reach install --system --channels opencli"
        )

    def _check_bili_cli(self):
        """bili-cli candidate. None = not installed."""
        probe = probe_command("bili", ["--version"], timeout=10, package="bilibili-cli")
        if probe.status == "missing":
            return None
        if probe.status == "broken":
            return "error", "bili 命令存在但无法执行\n" + probe.hint
        if not probe.ok:
            return "warn", f"bili-cli 探测失败（{probe.status}），运行 `bili status` 查看详情"
        return "ok", (
            "bili-cli 可用（搜索/热门/排行/视频详情/音频，无需登录；"
            "字幕需 OpenCLI。上游 2026-03 起停更）"
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
                "OpenCLI 桥接已连接，但 Bilibili 页面、登录态和实际命令"
                "未实时验证；Doctor 不执行平台命令，因此当前不标记为可用。"
            )
        return "warn", st.hint

    def _check_search_api(self):
        """Zero-dependency search API fallback. None = unreachable."""
        if not _search_api_ok():
            return None
        return "ok", (
            "B站搜索 API 可达（仅搜索，curl 直连）。"
            "完整功能建议安装 bili-cli：pipx install bilibili-cli"
        )

    # ── unified entry backends ──

    def _cli_search(self, *, query: str, limit: int, timeout: float) -> list:
        data = _bili_json(["search", query, "--type", "video", "-n", str(limit)], timeout)
        return [_cli_video_item(v) for v in (data if isinstance(data, list) else [])[:limit]]

    def _cli_read(self, *, target: str, timeout: float) -> list:
        data = _bili_json(["video", _bvid(target, timeout)], timeout)
        return [_cli_video_item(data.get("video") or {})]

    def _api_read(self, *, target: str, timeout: float) -> list:
        return [_api_video_item(_bili_api(f"/x/web-interface/view?bvid={_bvid(target, timeout)}", timeout))]

    def _cli_hot(self, *, limit: int, timeout: float) -> list:
        data = _bili_json(["hot", "-n", str(limit)], timeout)
        return [_cli_video_item(v) for v in (data.get("items") or [])[:limit]]

    def _api_hot(self, *, limit: int, timeout: float) -> list:
        data = _bili_api(f"/x/web-interface/popular?ps={limit}&pn=1", timeout)
        return [_api_video_item(v) for v in (data.get("list") or [])[:limit]]

    def _cli_subtitle(self, *, target: str, timeout: float) -> list:
        data = _bili_json(["video", _bvid(target, timeout), "--subtitle"], timeout)
        sub = data.get("subtitle") or {}
        if not sub.get("available"):
            if not (sessions_root() / "bili-cli" / ".bilibili-cli" / "credential.json").exists():
                raise ReachError(NEED_LOGIN, "Bilibili is not logged in", hint=_BILI_LOGIN_HINT)
            raise ReachError(NOT_FOUND, "this video has no subtitles")
        text = sub.get("text") or "\n".join(i.get("content", "") for i in sub.get("items") or [])
        return [_cli_video_item(data.get("video") or {}, text=text)]
