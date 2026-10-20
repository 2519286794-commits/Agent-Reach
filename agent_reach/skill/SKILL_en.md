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
| `UPSTREAM_BROKEN` | Channel is down right now. Suggest the user run `agent-reach update` once (upstream may already be fixed); if it still fails, tell them, and don't retry in a loop |
| `TIMEOUT` / `RATE_LIMITED` | Retry later |
| `NOT_FOUND` / `BAD_INPUT` | Check the link or args; run `agent-reach channels` if needed |

## Rules

1. If your own web search / fetch works, use it first; the `web` channel is a fallback.
2. Say "using agent-reach channel X" before you start.
3. For multi-platform research, call several channels in parallel, then summarize.
4. Read only. Never post, comment, or like.

## Channels

{{CHANNEL_TABLE}}

`default` channels work right away; others need `agent-reach add <channel>` first. Default channels can be removed too; updates never add a removed one back.

## Browser

Xiaohongshu, Reddit, Twitter, Boss Zhipin, Xueqiu hot posts and similar channels use the dedicated Agent Reach browser. It opens by itself; you never start it. The first open can take about 40 seconds, so don't treat that as a hang. It closes after 10 minutes without use.

## When the user wants to manage Agent Reach

| User asks | You run |
|---|---|
| Status / what works | `agent-reach doctor --text` (for a live test, `agent-reach check --text`) |
| Add a platform ("add Xiaohongshu") | `agent-reach add <channel>`; one command installs everything it needs. Tell the user only what they must do: log in in the window that opens (`agent-reach login <channel>`), or provide a key |
| Login expired | `agent-reach login <channel>` (the user logs in) |
| Remove a platform / log out | `agent-reach remove <channel>` (default channels too) / `agent-reach logout <channel>` |
| Upgrade / update | `agent-reach update` (also upgrades every channel's tools to their latest versions), then report as in "When there is a new version" below |
| Uninstall | show `agent-reach uninstall --dry-run` first, then `agent-reach uninstall` once they confirm |
| Another AI should use it | `agent-reach skill link <that AI's skills folder>`; `agent-reach skill` shows where it is placed now |

First install: `agent-reach setup`.

## When there is a new version

Any result with `meta.update` means a newer version exists. Mention it once per conversation, in the user's language and plain words:

1. Agent Reach has a new version (`meta.update.latest`).
2. What changed: 1 to 3 short points taken from `meta.update.notes`.
3. Ask whether to update.

Run `agent-reach update` only after the user says yes; never update without it. Afterwards, tell them plainly again what changed, plus every sentence in `result.user_actions` (e.g. a channel now needs a login).
