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
| `NEED_SETUP` | a tool, key, prerequisite or the Agent Reach browser is missing | run `agent-reach doctor --text` and follow the problem listed for the channel: `agent-reach add <channel>`, install the missing prerequisite, `agent-reach browser setup`, or `agent-reach configure groq-key` |
| `NEED_LOGIN` | login is missing or expired | the user runs `agent-reach login <channel>` and logs in themselves; if it still fails, `agent-reach logout <channel>` then log in again |
| `UPSTREAM_BROKEN` | the upstream tool or platform failed | don't retry in a loop; try again later, run `agent-reach update` (newer pinned tools often fix this), then `agent-reach check <channel>`; still broken → open an issue with the `message` |
| `TIMEOUT` | no backend answered in time | retry later, or pass a larger `--timeout SECONDS`; on a restricted network set a proxy (below) |
| `RATE_LIMITED` | the platform is throttling | wait before retrying; avoid many requests in a row |
| `NOT_FOUND` | the content does not exist | check the link, id or username |
| `BAD_INPUT` | wrong arguments or unknown channel/action | run `agent-reach channels` for valid actions and usage |

## Doctor statuses

| Status | Meaning | What to do |
|---|---|---|
| `not_added` | optional channel not turned on | `agent-reach add <channel>` |
| `needs_setup` | something is missing; `problems` says what | follow each problem: install prerequisite, `agent-reach add <channel>` again, `agent-reach browser setup`, or `agent-reach configure <key>` |
| `needs_login` | the last live check failed only on login | `agent-reach login <channel>` (the user logs in) |
| `unverified` | set up, but no live check in the last 24 hours | `agent-reach check <channel>` |
| `ready` | passed a live check in the last 24 hours | nothing |
| `broken` | the last live check failed for another reason | `agent-reach update`, then `agent-reach check <channel> --text`; see `UPSTREAM_BROKEN` |

`agent-reach doctor --live` runs the live checks first, then reports.

## Agent Reach browser

Used by xiaohongshu, reddit, twitter, facebook, instagram, boss and xueqiu. It is a separate Chrome window with its own profile in `~/.agent-reach/browser/`.

- **`agent-reach browser setup` keeps saying it is waiting for the extension**: in the Agent Reach window, click "Add to Chrome" on the OpenCLI extension page, then run `agent-reach browser setup` again.
- **"more than one new OpenCLI profile connected"**: close other Chrome windows that have the OpenCLI extension, then run setup again.
- **Chrome not installed**: install Google Chrome, then retry.
- **Window closed**: `agent-reach browser start` reopens it; `agent-reach browser status` shows its state.
- Close the window when you're done; any local process can control it through its debugging port.

## Proxy

Some platforms block certain networks or regions. Save a proxy once (the address is asked for with hidden input, since it may contain a password):

```bash
agent-reach configure proxy
```

An agent without a terminal prompt can pipe the value in: `agent-reach configure proxy --stdin`.

It is used for every Agent Reach command. An `HTTPS_PROXY` set in your shell takes precedence.

## Still stuck

- `agent-reach update` and try again.
- Remove and re-add a channel: `agent-reach remove <channel>` then `agent-reach add <channel>` (this also clears its login).
- Open an issue at https://github.com/Panniantong/Agent-Reach/issues with the output of `agent-reach doctor --text` (it starts with the version) and `agent-reach check <channel> --text`. Remove any personal data first.
