# Install Agent Reach

For the AI doing the install. Run every command yourself. Each `agent-reach` command prints one JSON object (with `--text`: plain text for people); read `ok`, `result` and `error.hint`.

> ⚠️ The PyPI package named `agent-reach` is NOT this project. Never install it from PyPI; only use the GitHub URL below.

## 0. Before you start

- You must be able to run terminal commands. If you can't, tell the user: "Please turn on command execution for me in my settings, then ask again."
- Already have it (`command -v agent-reach` prints a path)? Check its installation source before replacing an existing build.
- `uv` missing (`uv --version` fails)? Tell the user: "I'm installing uv, a small tool that installs command-line programs. It needs no admin password." Then run:
  - macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - Still `uv: command not found`? Open a new shell and try again.

## 1. Install and set up

```bash
uv tool install --reinstall .  # run from this checkout; alternatively pass its built wheel path
agent-reach setup
agent-reach doctor --text
```

`agent-reach setup --text` prints the same compact capability table directly. Plain `setup` preserves the JSON contract and saves `installation-report.md` under the private Reach directory.

`agent-reach` not found after install? Run `uv tool update-shell` and open a new shell.

`setup` turns on the default channels (web, YouTube, GitHub, V2EX, Bilibili), installs the Skill, and registers the Reach MCP server in an existing Cursor profile. Run `agent-reach mcp status` to inspect that registration.

`doctor --text` reads local status without opening browsers or querying every platform. Installation is separate from acceptance. When the user needs a specific channel, use one bounded `check CHANNEL --search --text` or the requested formal action. Diagnose actual errors; a failure does not establish a platform-wide login requirement.

## 2. Report to the user

Present the generated compact report directly in the final response:

1. **Installation outcome**: the generated receipt includes the version and default dependency results. Do not repeat them or append the full agent-link list unless asked. An `ok: true` dependency install is not a live business check.
2. **Capabilities**: present `result.installation_report.markdown` unchanged: a local-time greeting, install outcome, icon legend, three-column table (platform / without login / try after login), and live-verification line. Keep failures and user removals visible. Do not append detailed matrices or internal action lists. ✅ describes public content, ❌ the listed authenticated Reach features, and — no additional login feature here. Sign-in is no guarantee of access; network failures and untested actions are not login requirements. The report link is supplementary.
3. **Optional capabilities**: add only for a missing capability or explicit setup request. `login_if_required` and `logins[].when=only_if_required` are conditional, not a to-do list. Existing public content remains available if login is skipped.
4. **Example, Reddit**: public search, bodies and some comments can be attempted with existing web tools. Reach browser actions add search, post reading and subreddit lists; reuse an authorized session and log in only when the selected path requires it. Full comment trees, all replies and writing comments are outside the guarantee.
5. **Later management**: the user can say 'add Xiaohongshu' or 'remove V2EX'. Default channels can be removed too.

Before selecting Reach for a platform mention, check whether existing public tools already satisfy the task. For a structured/site-specific action, use its declared Reach route directly; no redundant search is required.

When the user asks for a channel, run `agent-reach ensure <channel>` or MCP `reach_ensure`. Reach installs missing dependencies, checks existing sessions and runs the formal action. For OpenCLI select a connected existing profile with `agent-reach browser use ID`. To authorize a site-scoped Cloak import, run `agent-reach ensure <channel> --reuse-profile ID`; this selection is remembered. If a query returns `operation_id`, the user completes login or verification and the agent calls `resume`. Boss's native CLI fallback needs CDP; Cloak does not. Install the runtime and Skill from the same build.

For the optional one-sentence CLI, save an OpenAI-compatible model with `agent-reach configure model-key --stdin`, `configure model-base-url URL`, and `configure model-name NAME`; then use `agent-reach ask "find and summarize ..."`. Direct channel commands and MCP tools do not require this model key.

Problems: [troubleshooting.md](troubleshooting.md).
