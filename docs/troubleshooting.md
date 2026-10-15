# Troubleshooting

Start with:

```bash
agent-reach doctor --text     # offline status of every channel
agent-reach check <channel> --text   # live test of one channel
```

## Error codes

Every failed command returns `ok: false` and an `error` with `code`, `message` and `hint`. The `hint` is usually the exact next step.

| Code | Meaning | What to do |
|---|---|---|
| `NEED_SETUP` | a tool, key or the Agent Reach browser is missing | run `agent-reach doctor --text` and follow the problem listed for the channel: usually `agent-reach add <channel>` again (it installs whatever is missing), `agent-reach browser setup`, or `agent-reach configure groq-key` |
| `NEED_LOGIN` | login is missing or expired | the user runs `agent-reach login <channel>` and logs in themselves; if it still fails, `agent-reach logout <channel>` then log in again |
| `UPSTREAM_BROKEN` | the upstream tool or platform failed | don't retry in a loop; try again later, run `agent-reach update` (it upgrades the channel's tools to their latest versions, which often fixes this), then `agent-reach check <channel>`; still broken → open an issue with the `message` |
| `TIMEOUT` | no backend answered in time | retry later, or pass a larger `--timeout SECONDS`; on a restricted network set a proxy (below) |
| `RATE_LIMITED` | the platform is throttling | wait before retrying; avoid many requests in a row |
| `NOT_FOUND` | the content does not exist | check the link, id or username |
| `BAD_INPUT` | wrong arguments or unknown channel/action | run `agent-reach channels` for valid actions and usage |

## Doctor statuses

| Status | Meaning | What to do |
|---|---|---|
| `not_added` | optional channel not turned on | `agent-reach add <channel>` |
| `needs_setup` | something is missing; `problems` says what | follow each problem: `agent-reach add <channel>` again, `agent-reach browser setup`, or `agent-reach configure <key>` |
| `needs_login` | the last live check failed only on login | `agent-reach login <channel>` (the user logs in) |
| `unverified` | set up, but no live check in the last 24 hours | `agent-reach check <channel>` |
| `ready` | passed a live check in the last 24 hours | nothing |
| `broken` | the last live check failed for another reason | `agent-reach update`, then `agent-reach check <channel> --text`; see `UPSTREAM_BROKEN` |

Run `agent-reach check` first if you want fresh live results. In the `doctor` output, `regressed: true` on a channel means an action passed in the previous check and fails in the latest one.

## Tool versions

Agent Reach installs the latest version of each channel's tools; it does not pin them. `agent-reach doctor` shows the version actually installed for each tool. If an upstream release turns out to be broken, a new Agent Reach release excludes that version (and may set a minimum); `agent-reach update` then moves you to a good one. Until that release exists, roll back as below or wait.

## Agent Reach browser

Used by xiaohongshu, reddit, twitter, facebook, instagram, boss and xueqiu. It is a separate Chrome window with its own profile in `~/.agent-reach/browser/`. It opens by itself when one of these channels needs it (the first open can take about 40 seconds) and closes after 10 minutes without Agent Reach use.

- **The extension did not connect**: run `agent-reach browser setup`; on macOS and Linux it loads the OpenCLI extension by itself. On Windows, click "Add to Chrome" once on the OpenCLI extension page in the window that opens, then run `agent-reach browser setup` again.
- **"more than one new OpenCLI profile connected"**: close other Chrome windows that have the OpenCLI extension, then run setup again.
- **No Chrome on the machine**: nothing to do; Agent Reach downloads its own copy (Chrome for Testing) into `~/.agent-reach/tools/chrome/`.
- **Window closed by hand**: nothing to do; the next command that needs it opens it again. `agent-reach browser status` shows its state.
- While it is open, any local process can control it through its debugging port; it closes itself after 10 idle minutes.

## Skill not picked up by an AI

`agent-reach skill` shows the one real copy of the instructions (`~/.agents/skills/agent-reach/SKILL.md`) and the links made for other AIs. An AI not covered automatically: `agent-reach skill link <its skills folder>`. On Windows, where links may not be allowed, a copy is made instead and refreshed by `agent-reach update`.

## Install, update and roll back

Agent Reach is installed with uv only. If `agent-reach update` says the program was installed another way, reinstall once as in [install.md](install.md); your channels, keys and logins under `~/.agent-reach/` are kept.

A new version broke something? Go back to the previous release, then line the tools and skill up with it:

```bash
uv tool install --force https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v<previous>.zip
agent-reach update --sync-only
```

Removed default channels stay removed across updates; `agent-reach add <channel>` brings one back.

## Proxy

Some platforms block certain networks or regions. Save a proxy once (the address is asked for with hidden input, since it may contain a password):

```bash
agent-reach configure proxy
```

An agent without a terminal prompt can pipe the value in: `agent-reach configure proxy --stdin`.

It is used for every Agent Reach command. An `HTTPS_PROXY` set in your shell takes precedence.

## Still stuck

- `agent-reach update` and try again.
- Remove and re-add a channel: `agent-reach remove <channel>` then `agent-reach add <channel>` (remove also clears its login, its site cookies in the Agent Reach browser, and its private tools nobody else uses).
- Open an issue at https://github.com/Panniantong/Agent-Reach/issues with the output of `agent-reach doctor --text` (it starts with the version) and `agent-reach check <channel> --text`. Remove any personal data first.
