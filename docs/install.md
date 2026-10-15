# Install Agent Reach

For the AI doing the install. Run every command yourself. Each `agent-reach` command prints one JSON object (with `--text`: plain text for people); read `ok`, `result` and `error.hint`.

> ⚠️ The PyPI package named `agent-reach` is NOT this project. Never install it from PyPI; only use the GitHub URL below.

## 0. Before you start

- You must be able to run terminal commands. If you can't, tell the user: "Please turn on command execution for me in my settings, then ask again."
- Already have it (`command -v agent-reach` prints a path)? Run `agent-reach update` and stop here. Coming from 1.5 or earlier: follow [update.md](update.md).
- `uv` missing (`uv --version` fails)? Tell the user: "I'm installing uv, a small tool that installs command-line programs. It needs no admin password." Then run:
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - Still `uv: command not found`? Open a new shell and try again.

## 1. Install and set up

```bash
uv tool install https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v1.6.0.zip
agent-reach setup
agent-reach check --text
```

`agent-reach` not found after install? Run `uv tool update-shell` and open a new shell.

`setup` takes about 20 s, `check` about 1 minute; allow a timeout of at least 3 minutes. `setup` turns on the default channels (web, YouTube, GitHub, V2EX, Bilibili) and gives the AIs found on this machine the Agent Reach instructions (a "skill").

`check --text` tests the channels that are on and exits 1 if any action fails. A `NEED_LOGIN` failure (e.g. Bilibili subtitles) is normal: that feature needs an optional login. Any other failure: tell the user which feature does not work yet.

## 2. Report to the user

Keep it short and plain:

1. **Works now**: the channels in `result.default_channels` with `ok: true`. Mention features that failed `check` only as "needs login" or "not working yet".
2. **Which AIs can use it**: `result.skill.agents` (the AIs found on this machine).
3. **Optional, add any time**: each entry of `result.optional_channels`. Say only what the user will have to do: log in, or get a key (`groq-key`: a free key from https://console.groq.com). Anything else a channel needs (Node.js, Chrome, ffmpeg, the browser extension) is installed by Agent Reach itself, with no admin password. Mention that `experimental` ones can break at any time. Optional logins for channels already on: `result.logins` (e.g. Bilibili login unlocks subtitles).
4. **How to add or remove one later**: "Just tell me, e.g. 'add Xiaohongshu' or 'remove V2EX'." Default channels can be removed too.

When the user asks for a channel, run `agent-reach add <channel>`; it installs everything the channel needs. Then tell the user only what is left for them: logging in (`agent-reach login <channel>` opens a window; they log in there) or entering a key. Browser channels set up the Agent Reach browser and its extension by themselves; on Windows the user clicks "Add to Chrome" once in the window that opens. Never log in for the user, never ask for their password, never read their browser's cookies. Suggest a secondary account. Keys are entered by the user in their own terminal with `agent-reach configure groq-key` (hidden input); if you must run it yourself, pipe the value: `agent-reach configure groq-key --stdin`.

Problems: [troubleshooting.md](troubleshooting.md).
