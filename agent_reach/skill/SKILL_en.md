---
name: agent-reach
description: >
  Use when the user wants content from platforms your own tools can't reach:
  Xiaohongshu, Bilibili, Twitter/X, Reddit, Facebook, Instagram, YouTube
  (subtitles, transcripts), Xiaoyuzhou podcasts, V2EX, Xueqiu stock quotes,
  GitHub, LinkedIn / Boss Zhipin jobs, or when your built-in web search / fetch
  is missing or fails. Read-only: never post, comment, like, or log in on the
  user's behalf.
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: "{{VERSION}}"
---

# Agent Reach

One command for every platform: `agent-reach`. Read-only; output is always one JSON object.

## Usage

```bash
agent-reach channels                      # actions and params per channel (run this when unsure)
agent-reach <channel> <action> [args]     # e.g. agent-reach reddit search "rust async" --limit 5
agent-reach read <url>                    # picks the channel from the URL
```

Results:

- `ok: true` → content in `items`; each has `title / url / author / published_at / text`, upstream data in `raw`.
- `ok: false` → branch on `error.code` and follow `error.hint`:

| error.code | What to do |
|---|---|
| `NEED_SETUP` | Tell the user the command in the hint (usually `agent-reach add <channel>`) |
| `NEED_LOGIN` | The user logs in themselves (`agent-reach login <channel>`). **Never log in for them or read their browser cookies** |
| `UPSTREAM_BROKEN` | Channel is down right now; tell the user, don't retry in a loop |
| `TIMEOUT` / `RATE_LIMITED` | Retry later |
| `NOT_FOUND` / `BAD_INPUT` | Check the link or args; run `agent-reach channels` if needed |

## Rules

1. If your own web search / fetch works, use it first; the `web` channel is a fallback.
2. Say "using agent-reach channel X" before you start.
3. For multi-platform research, call several channels in parallel, then summarize.
4. Read only. Never post, comment, or like.

## Channels

{{CHANNEL_TABLE}}

`default` channels work right away; others need `agent-reach add <channel>` first.

## Management commands (for the user)

`agent-reach setup` (first run) · `add` / `remove <channel>` · `login` / `logout <channel>` · `doctor` · `update` · `uninstall`
