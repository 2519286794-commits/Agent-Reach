# -*- coding: utf-8 -*-
"""Xiaoyuzhou Podcast (小宇宙播客) — transcribe podcasts via Groq Whisper API."""

import os
import shutil
import tempfile

from agent_reach.config import Config
from agent_reach.probe import probe_command
from agent_reach.runtime.result import BAD_INPUT, NEED_SETUP, ReachError, make_item
from agent_reach.runtime.run import run_cmd

from .base import Action, Channel, Param

_SCRIPT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "transcribe_xiaoyuzhou.sh")


class XiaoyuzhouChannel(Channel):
    name = "xiaoyuzhou"
    description = "小宇宙播客转文字"
    backends = ["groq-whisper", "ffmpeg"]
    tier = 1

    level = "optional"
    actions = (
        Action(
            "transcribe",
            "Full transcript of a podcast episode (uses Groq Whisper quota)",
            (Param("target", "episode link"),),
            (("groq-whisper", "_script_transcribe"),),
            timeout=900,
        ),
    )

    def can_handle(self, url: str) -> bool:
        from agent_reach.utils.url import host_matches

        return host_matches(url, "xiaoyuzhoufm.com")

    def check(self, config=None):
        self.active_backend = None

        # Check ffmpeg — really execute it: a stale pip-installed ffmpeg shim
        # passes shutil.which() but cannot run
        probe = probe_command("ffmpeg", ["-version"], timeout=10, package="ffmpeg")
        if probe.status == "missing":
            return "off", (
                "需要 ffmpeg（音频转码和切片）。安装：\n"
                "  Ubuntu/Debian: apt install -y ffmpeg\n"
                "  macOS: brew install ffmpeg"
            )
        if not probe.ok:
            return "error", (
                "ffmpeg 无法执行，重装：brew install ffmpeg（macOS）/ apt install ffmpeg（Linux）"
            )

        # Check script exists
        script = os.path.expanduser("~/.agent-reach/tools/xiaoyuzhou/transcribe.sh")
        if not os.path.isfile(script):
            return "off", (
                "转录脚本未安装。运行：\n"
                "  agent-reach install --env=auto --system --channels=xiaoyuzhou\n"
                "  或手动复制 transcribe.sh 到 ~/.agent-reach/tools/xiaoyuzhou/"
            )

        # Check GROQ_API_KEY — prefer env var, fall back to Agent Reach config
        has_key = bool(os.environ.get("GROQ_API_KEY"))
        if not has_key:
            try:
                cfg = config if config is not None else Config()
                has_key = bool(cfg.get("groq_api_key"))
            except Exception:
                has_key = False
        if not has_key:
            return "warn", (
                "需要配置 Groq API Key（免费）。步骤：\n"
                "  1. 注册 https://console.groq.com\n"
                "  2. 运行: agent-reach configure groq-key（隐藏输入）"
            )

        self.active_backend = "groq-whisper"
        return "ok", "完整可用（播客下载 + Whisper 转录）"

    # ── unified entry backends ──

    def _script_transcribe(self, *, target: str, timeout: float) -> list:
        from agent_reach.utils.url import host_matches

        if not host_matches(str(target).strip(), "xiaoyuzhoufm.com"):
            raise ReachError(BAD_INPUT, "target must be a xiaoyuzhoufm.com episode link")
        key = os.environ.get("GROQ_API_KEY") or Config(read_only=True).get("groq_api_key")
        if not key:
            raise ReachError(
                NEED_SETUP, "no Groq API key configured",
                hint="Ask the user for a free key from https://console.groq.com, then run `agent-reach configure groq-key`.",
            )
        if not shutil.which("ffmpeg"):
            raise ReachError(NEED_SETUP, "ffmpeg is not installed", hint="Ask the user to install ffmpeg (macOS: brew install ffmpeg).")
        with tempfile.TemporaryDirectory(prefix="agent-reach-xyz-") as tmp:
            out = os.path.join(tmp, "transcript.txt")
            run_cmd(["bash", _SCRIPT, str(target).strip(), out], timeout=timeout, env={"GROQ_API_KEY": str(key)}, label="transcribe")
            with open(out, encoding="utf-8", errors="replace") as fh:
                text = fh.read().strip()
        return [make_item(url=str(target).strip(), text=text)]
