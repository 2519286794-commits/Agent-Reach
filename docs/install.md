# Install Agent Reach

Instructions for the AI agent doing the install. Run the commands yourself; ask the user only where a step says so. Every `agent-reach` command prints one JSON object; read `ok`, `result` and `error.hint`.

> ⚠️ The PyPI package named `agent-reach` is NOT this project. Never install it from PyPI; only use the GitHub URL below.

## 1. Install the program

Already installed? Run `agent-reach update` instead and stop here (see [update.md](update.md)).

```bash
uv tool install https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v2.0.0.zip
```

No `uv`? Use pipx with the same URL:

```bash
pipx install https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v2.0.0.zip
```

If `agent-reach` is not found afterwards, run `uv tool update-shell` (or `pipx ensurepath`) and open a new shell.

## 2. Set up

```bash
agent-reach setup
```

This checks prerequisites, installs the Agent Reach skill into your skill folder, and keeps keys from an older install. The default channels (github, youtube, v2ex, web) work now.

If `result.prerequisites` shows something missing (node, git, chrome, ffmpeg, uv), tell the user the `hint`; only the channels that need it are affected.

## 3. Let the user pick optional channels

Show the user `result.optional_channels` from the setup output, with what each `needs`. Mention that `experimental` channels can break at any time. Then, for each channel they pick:

```bash
agent-reach add <channel>
```

Follow the `result.next` list it returns.

## 4. Logins and keys (the user does these)

Never log in for the user, never ask for their password, never read their browser's cookies.

**Browser channels** (xiaohongshu, reddit, twitter, facebook, instagram, boss, xueqiu): once, first run

```bash
agent-reach browser setup
```

It opens the Agent Reach browser (a separate Chrome window) at the OpenCLI extension page. Ask the user to click "Add to Chrome" there, then run `agent-reach browser setup` again until `ok` is true. Then for each channel:

```bash
agent-reach login <channel>
```

The login page opens in the Agent Reach browser; the user logs in. If the output says to, run `agent-reach login <channel> --sync` after they are done.

**bilibili / linkedin**: `agent-reach login <channel>` runs the tool's own login (QR code or a browser window). Run it where the user can see the output.

**Keys** (xiaoyuzhou, youtube transcribe): ask the user to get a free key at https://console.groq.com and run this in their own terminal (hidden input):

```bash
agent-reach configure groq-key
```

If you must run it yourself, pipe the value: `agent-reach configure groq-key --stdin`.

Suggest a secondary account for login channels.

## 5. Verify

```bash
agent-reach check --text
agent-reach doctor --text
```

Report to the user what is `ready` and what still needs something. Fixes for each status and error code: [troubleshooting.md](troubleshooting.md).
