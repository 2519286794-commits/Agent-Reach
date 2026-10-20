---
name: agent-reach
description: >
  Use when the user wants content from platforms your own tools can't reach:
  小红书/xiaohongshu, B站/bilibili, Twitter/X, Reddit, Facebook, Instagram,
  YouTube (subtitles, transcripts), 小宇宙播客, V2EX, 雪球/股票行情, GitHub, LinkedIn/Boss直聘 jobs,
  or when your built-in web search / fetch is missing or fails.
  Read-only: never post, comment, like, or log in on the user's behalf.
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: "{{VERSION}}"
---

# Agent Reach

一个命令接所有平台：`agent-reach`。只读，输出永远是一段 JSON。

## 怎么用

```bash
agent-reach channels                      # 每个渠道有哪些动作、要什么参数（不确定就先跑这个）
agent-reach <渠道> <动作> [参数]          # 例：agent-reach xiaohongshu search "咖啡" --limit 5
agent-reach read <链接>                   # 给链接，自动认出渠道
```

结果：

- `ok: true` → 内容在 `items` 里，每条有 `title / url / author / published_at / text`，原始数据在 `raw`。
- `ok: false` → 看 `error.code`，按 `error.hint` 做：

| error.code | 怎么办 |
|---|---|
| `NEED_SETUP` | 告诉用户 hint 里的命令（常见：`agent-reach add <渠道>`） |
| `NEED_LOGIN` | 让用户自己登录（`agent-reach login <渠道>`），**绝不替用户登录、不读用户浏览器的 Cookie** |
| `UPSTREAM_BROKEN` | 这个渠道暂时不可用。先建议用户运行一次 `agent-reach update`（上游可能已经修好）；还不行就告诉用户，不要反复重试 |
| `TIMEOUT` / `RATE_LIMITED` | 稍后再试 |
| `NOT_FOUND` / `BAD_INPUT` | 检查链接或参数，必要时跑 `agent-reach channels` |

## 规则

1. 你自己有能用的网页搜索 / 读网页工具就先用自己的；`web` 渠道只当保底。
2. 开始前说一句"用 agent-reach 的 X 渠道"。
3. 多平台调研时并行调几个渠道再汇总。
4. 只做读取。发帖、评论、点赞一律不做。

## 渠道

{{CHANNEL_TABLE}}

`default` 装好就能用；其余要用户先 `agent-reach add <渠道>`。默认渠道也可以去掉，去掉后更新不会再加回来。

## 浏览器

小红书、Reddit、Twitter、Boss直聘、雪球热帖等渠道要用 Agent Reach 专用浏览器。它会自己打开，不用你启动；第一次打开大约要 40 秒，别当成卡住。10 分钟没用会自动关掉。

## 用户要管理 Agent Reach 时

| 用户说 | 你运行 |
|---|---|
| 看看状态 / 哪些能用 | `agent-reach doctor --text`（要实测再跑 `agent-reach check --text`） |
| 加上某个平台（如"加上小红书"） | `agent-reach add <渠道>`，一条命令就装好它需要的一切。只告诉用户他本人要做的事：在弹出的窗口里登录（`agent-reach login <渠道>`），或者提供一个 Key |
| 登录过期了 | `agent-reach login <渠道>`（用户本人登录） |
| 去掉某个平台 / 退出登录 | `agent-reach remove <渠道>`（默认渠道也能去掉）/ `agent-reach logout <渠道>` |
| 升级 / 更新 | `agent-reach update`（同时把各渠道的工具升到最新），然后按下面"有新版本时"把结果告诉用户 |
| 卸载 | 先 `agent-reach uninstall --dry-run` 给用户看，确认后 `agent-reach uninstall` |
| 让另一个 AI 也能用 | `agent-reach skill link <那个 AI 的 skill 目录>`；`agent-reach skill` 查看现在放在哪 |

首次安装：`agent-reach setup`。

## 有新版本时

任何结果里出现 `meta.update`，就说明有新版本。每次对话只提一次，用用户的语言、大白话：

1. 告诉用户 Agent Reach 有新版本（`meta.update.latest`）。
2. 从 `meta.update.notes` 里挑 1 到 3 个简短要点，说清楚这次改了什么。
3. 问用户要不要更新。

用户说要，才运行 `agent-reach update`；没得到同意绝不更新。更新完再用大白话说一遍改了什么，并把 `result.user_actions` 里每一条（比如某个渠道要重新登录）告诉用户。
