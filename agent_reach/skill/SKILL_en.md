---
name: agent-reach
description: >
  Use when the user names a supported platform, shares its URL, or asks to configure or diagnose its channel:
  Xiaohongshu, Bilibili, Twitter/X, Reddit, Facebook, Instagram, YouTube
  (subtitles, transcripts), V2EX, Xueqiu stock quotes,
  GitHub, LinkedIn / Boss Zhipin jobs,
  or when your built-in web search / fetch
  is missing or fails. Read-only: never post, comment, like, or log in on the
  user's behalf.
  Supplement existing agent capabilities: prefer available public web tools on every platform.
  Use Reach for missing evidence, unavailable tools or declared structured actions.
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: "{{VERSION}}"
---

# Agent Reach

One command for every platform: `agent-reach`. Read-only; JSON by default, or a human-readable installation report with `setup --text`.

## Compact installation handoff

Present `result.installation_report.markdown` directly: a greeting generated from the installing computer's local clock, the install outcome, an icon legend, one three-column table (platform / content without login / features to try after login), and one verification line. Do not add another greeting, detailed matrices or internal action lists. Load [Capability scope](references/capabilities.md) only when the user asks for detail.

Use JSON `agent-reach setup`, or `setup --text` for direct terminal output. A report link is supplementary. Preserve failed installs, user removals and states requiring attention. ✅ marks content to try without login; ❌ marks the listed authenticated Reach features, with no promise that login guarantees access; — means no additional login feature here. Public Reddit search, post bodies and available comments use existing web tools without login; do not promise complete comment trees.

Local greeting hours: morning 05–10, noon 11–13, afternoon 14–17, evening 18–21, late night otherwise. No geolocation or timezone question is needed. Name concrete content and actions; avoid vague phrases such as "when the page asks," "more site features" or "some tweets." Network failures, untested paths and unsupported actions must not become ❌ login requirements. If `installation_report` is missing, check the build/source.

Keep feature labels short: "read posts, view replies" or "view posts, trending stocks." Preserve distinctions between snippets, links and full text; trending stocks are not investment picks. State shared comment coverage and subtitle availability once below the table.

## Usage

Route by the evidence needed, on every platform:

1. For public information, open supplied links with existing web tools or search with an optional site filter. Check body text, comments and subtitles separately. Answer when sufficient; no channel setup or login is needed.
2. Use a declared Reach action when evidence is missing, existing tools are unavailable, or a structured/site-specific operation is requested. Inspect `agent-reach channels` when needed. Reuse available anonymous native tools or public APIs directly; do not force a redundant web search before a suitable action. Reach `web search` / `web read` provide an anonymous fallback.
3. Load [Sessions](references/sessions.md) only when the remaining task's chosen path actually requires authentication or session setup. Reuse authorized sessions before requesting login. Missing browser setup, 403, challenges, DNS/TLS failures, rate limits and timeouts need their own diagnosis. A login button beside readable content is not a login wall.
4. Keep public evidence and deliver it even if login is skipped. Identify the remaining gap. Counts, subtitle track lists, page shells and search snippets do not establish comment text, subtitle text or complete bodies.

A platform name or URL identifies a source; it does not automatically trigger installation, ensure or login. Read Sessions for explicit setup/login/import/logout requests and [Maintenance](references/maintenance.md) for failures/updates/uninstall.

Public Reddit JSON may expose parent IDs; verify actual coverage. YouTube/Bilibili descriptions, subtitles and video content are separate evidence. Public X posts and reply streams are separate capabilities. Do not generalize a local failure into a platform-wide login requirement, or promise universal anonymous access. Distinguish local HTTP, proxy and built-in web-tool results.


```bash
agent-reach channels                      # actions and params per channel (run this when unsure)
agent-reach ensure <channel>             # setup, authorized reuse, live check
agent-reach <channel> <action> [args]     # e.g. agent-reach bilibili search "rust async" --limit 5
agent-reach read <url>                    # picks the channel from the URL
```

Results:

- `ok: true` → content in `items`; each has `title / url / author / published_at / text`, upstream data in `raw`.
- `ok: false` → branch on `error.code` and follow `error.hint`:

| error.code | What to do |
|---|---|
| `NEED_LOGIN` | Keep public results. If the remaining task needs this path, the user logs in; resume using `operation_id` |
| `UPSTREAM_BROKEN` | Channel is down right now; tell the user, don't retry in a loop |
| `TIMEOUT` | Inspect the failed stage and channel status; do not reopen or retry in a loop |
| `RATE_LIMITED` | Respect `retry_after_seconds`; the runtime pauses this channel |
| `NOT_FOUND` / `BAD_INPUT` | Check the link or args; run `agent-reach channels` if needed |

## Rules

1. On every platform, check whether existing public capabilities satisfy the request; use Reach for the missing capability. Declared structured/site-specific actions may be selected directly; authentication depends on the actual path.
2. Say "using agent-reach channel X" before calling a Reach channel.
3. Serialize commands sharing one browser profile; independent sessions may run in parallel.
4. Read only. Never post, comment, or like.
5. Never extract login state implicitly. Explicit authorization permits importing only the selected site's state. Never output cookies, tokens or credentials. Do not ask again for existing authorization.

## Channels

{{CHANNEL_TABLE}}

The login column lists authentication entry points, not prerequisites for public access. Requirements depend on the selected action. `default` means installed by default, not guaranteed network reachability; `ensure` prepares optional channels when needed. Reddit's public web path needs no Reddit channel setup. Default channels can be removed too; updates never add a removed one back.



## Reuse before login


`setup` installs defaults; adding a browser channel prepares the shared browser and extension. `login CHANNEL` opens the site for the user to log in. Imports are one-time and explicitly authorized; verify the requested action after import.


XHS read returns text descriptions, not image/video understanding. Never guess BOSS salary digits when salary_encoded=true; read the job detail instead.


Stop on PLATFORM_BLOCKED/RATE_LIMITED/NEED_LOGIN/BUSY. Serialize commands sharing a profile. Use `check CHANNEL --search` for live verification. See [Maintenance](references/maintenance.md) for dependency repair and distribution. Never modify dependencies during queries.

## When the user wants to manage Agent Reach

| User asks | You run |
|---|---|
| Status / what works | `agent-reach doctor --text` (for a live test, `agent-reach check <channel> --search --text`) |
| Add a platform ("add Xiaohongshu") | `agent-reach add <channel>`; one command installs everything it needs. Tell the user only what they must do: follow the login instructions (`agent-reach login <channel>`), or provide a key |
| Login expired | Read Sessions first; `agent-reach login <channel>` opens the shared browser for the user to log in |
| Remove a platform / log out | `agent-reach remove <channel>`; read Sessions before logout. `agent-reach logout <channel>` clears only that site in the shared browser |
| Upgrade / update | Read [Maintenance](references/maintenance.md), check the installation source, then update from the same source |
| Uninstall | show `agent-reach uninstall --dry-run` first, then `agent-reach uninstall` once they confirm |
| Another AI should use it | `agent-reach skill link <that AI's skills folder>`; `agent-reach skill` shows where it is placed now |

Follow the required installation handoff above. Ordinary queries load [Capability scope](references/capabilities.md) only when needed and do not install every optional channel.

## When there is a new version

Any result with `meta.update` means a newer version exists. Mention it once per conversation, in the user's language and plain words:

1. Agent Reach has a new version (`meta.update.latest`).
2. What changed: 1 to 3 short points taken from `meta.update.notes`.
3. Ask whether to update.

After the user agrees, read [Maintenance](references/maintenance.md) and confirm the installation source. Update from the same source, then report the actual changes and remaining user actions.


## Shared dedicated browser

All browser channels use `~/.agent-reach/browser/profile`. CloakBrowser is preferred; installation/download failure falls back to installed Chrome. OpenCLI prepares the extension and performs website extraction. BOSS uses the same dedicated browser. The idle watcher closes it after ten minutes; the next action reopens it.

Use `agent-reach execute CHANNEL ACTION --params '{...}'` to prepare and perform the real action once. Reserve `ensure CHANNEL` for setup checks and diagnosis. After the user completes a requested login, use `agent-reach resume OPERATION_ID` when an operation ID was returned. There is no Reach MCP server or model planner in this version, and no model API key is required.

Reuse the dedicated browser's saved login first. Explicit one-time site imports use `agent-reach browser import CHANNEL --opencli-profile ID` or `--state-file FILE`; they do not grant continuing access to personal Chrome. Verify the requested action after import. See [Sessions](references/sessions.md).

`add CHANNEL` prepares dependencies, browser and extension. `remove CHANNEL` clears only that site's login/storage, preserving other sites. Xiaoyuzhou remains an optional transcription channel requiring a Groq key.
