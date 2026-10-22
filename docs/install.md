# Install Agent Reach

For the AI doing the install. Run every command yourself. Each `agent-reach` command (1.6 and later) prints one JSON object; read `ok`, `result` and `error.hint`.

> ⚠️ The PyPI package named `agent-reach` is NOT this project. Never install it from PyPI; only use the GitHub URL below.

## 0. Before you start

- You must be able to run terminal commands. If you can't, tell the user: "Please turn on command execution for me in my settings, then ask again."
- Already installed (`command -v agent-reach` prints a path)? Run `agent-reach version`:
  - it prints JSON → run `agent-reach update` and stop here.
  - it prints a plain line like `Agent Reach v1.5.0` → this is an old version; follow [update.md](update.md) instead.
- `uv` missing (`uv --version` fails)? Tell the user: "I'm installing uv, a small tool that installs command-line programs. It needs no admin password." Then run:
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - Still `uv: command not found`? Open a new shell and try again.

## 1. Install and set up

```bash
uv tool install https://github.com/Panniantong/Agent-Reach/releases/latest/download/agent-reach.zip
agent-reach setup
```

`agent-reach` not found after install? Run `uv tool update-shell` and open a new shell.

`setup` turns on the default channels and installs the agent skill.

## 2. Report to the user

Show `result.installation_report.markdown` to the user as is. The program generates it; do not rewrite, reorder or add to it.

## 3. Later

- The user just says what they want, e.g. "add Xiaohongshu" → `agent-reach add <channel>`; "remove V2EX" → `agent-reach remove <channel>`.
- Keys are entered by the user, e.g. a Groq key for Xiaoyuzhou transcription: `agent-reach configure groq-key`.
- Everything else (usage, login, browser) is covered by the installed skill.

Problems: [troubleshooting.md](troubleshooting.md).
