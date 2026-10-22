# Update Agent Reach

For the AI doing the update. Run every command yourself.

## 1. Which version is installed?

```bash
agent-reach version
```

- Prints JSON (1.6 and later) → go to step 2.
- Prints a plain line like `Agent Reach v1.5.0`, or `agent-reach update` says "invalid choice" → it is 1.5 or earlier; go to step 3.
- `agent-reach` not found → follow [install.md](install.md).

## 2. Update (1.6 and later)

```bash
agent-reach update
```

It upgrades the program, every added channel's tools and the skill, and removes old copies. Show the user each line of `result.user_actions`, and `result.installation_report.markdown` as is when it is present. Then `agent-reach check --text` confirms the channels still work.

If it fails, `error.hint` holds the exact command to run.

## 3. Upgrade from 1.5 or earlier

1.6 is installed with uv, a small tool that installs command-line programs; 1.5 was installed with pipx or pip. Tell the user: "This is a big upgrade. Your keys and settings are kept; I'm moving Agent Reach to the new installer." Then:

1. `uv --version` fails? Install uv (no admin password):
   - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
2. Install 1.6:
   ```bash
   uv tool install --force https://github.com/Panniantong/Agent-Reach/releases/latest/download/agent-reach.zip
   ```
3. Open a new shell and check `agent-reach version` prints JSON. If it still prints the old line, run `uv tool update-shell`, open a new shell and check again.
4. Set it up:
   ```bash
   agent-reach setup
   ```
   It keeps `~/.agent-reach/config.yaml`, removes the old Agent Reach program (only Agent Reach itself, never the user's other tools) and refreshes the skill for every AI.
5. Show `result.installation_report.markdown` to the user as is. It explains what changed and which old channels they can add back.

## Roll back

A new version misbehaves? Go back to the previous one (replace `<previous>` with its number, e.g. `1.6.0`):

```bash
uv tool install --force https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v<previous>.zip
agent-reach update --sync-only
```

Channels, keys and logins under `~/.agent-reach/` are kept.
