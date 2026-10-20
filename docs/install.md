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

**This branch is an unpublished 1.6.0 candidate.** The latest verified official release is v1.5.0 and does not include the candidate's browser/setup changes.

For the official stable version:

```bash
uv tool install https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v1.5.0.zip
```

Continue with the [v1.5.0 installation instructions](https://github.com/Panniantong/Agent-Reach/blob/v1.5.0/docs/install.md). Stop here for a stable install; do not run this candidate's commands against 1.5.0.

For this candidate's local test package, use the supplied wheel:

```bash
uv tool install --force /path/to/agent_reach-1.6.0-py3-none-any.whl
agent-reach setup
agent-reach doctor --text
```

Do not run the stable install command over a candidate. Once v1.6.0 has actually been released, the official URL can advance to that tag. Already-installed ordinary users run `agent-reach update` explicitly; local candidate users keep the candidate source until it is released.

`agent-reach setup --text` prints the same compact capability table directly. Plain `setup` preserves the JSON contract and saves `installation-report.md` under the private Reach directory.

`agent-reach` not found after install? Run `uv tool update-shell` and open a new shell.

`setup` turns on the default channels (web, YouTube, GitHub, V2EX, Bilibili) and installs the Skill. It does not register an MCP server or require a model key.

`doctor --text` reads local status without opening browsers or querying every platform. Installation is separate from acceptance. When the user needs a specific channel, use one bounded `check CHANNEL --search --text` or the requested formal action. Diagnose actual errors; a failure does not establish a platform-wide login requirement.

## 2. Report to the user

Present the generated compact report directly in the final response:

1. **Installation outcome**: the generated receipt includes the version and default dependency results. Do not repeat them or append the full agent-link list unless asked. An `ok: true` dependency install is not a live business check.
2. **Capabilities**: present `result.installation_report.markdown` unchanged: a local-time greeting, install outcome, icon legend, three-column table (platform / without login / try after login), and live-verification line. Keep failures and user removals visible. Do not append detailed matrices or internal action lists. ✅ describes public content, ❌ the listed authenticated Reach features, and — no additional login feature here. Sign-in is no guarantee of access; network failures and untested actions are not login requirements. The report link is supplementary.
3. **Optional capabilities**: add only for a missing capability or explicit setup request. `login_if_required` and `logins[].when=only_if_required` are conditional, not a to-do list. Existing public content remains available if login is skipped.
4. **Example, Reddit**: public search, bodies and some comments can be attempted with existing web tools. Reach browser actions add search, post reading and subreddit lists; reuse an authorized session and log in only when the selected path requires it. Full comment trees, all replies and writing comments are outside the guarantee.
5. **Later management**: the user can say 'add Xiaohongshu' or 'remove V2EX'. Default channels can be removed too.

Before selecting Reach for a platform mention, check whether existing public tools already satisfy the task. For a structured/site-specific action, use its declared Reach route directly; no redundant search is required.

When the user asks for a channel, run `agent-reach add <channel>`. Browser channels install Node, OpenCLI, the dedicated browser and its extension automatically. One profile under `~/.agent-reach/browser/profile` is shared by all sites. CloakBrowser is preferred; download failure falls back to installed Chrome. The owned browser closes after 10 idle minutes and reopens on the next action. The Chrome fallback on Windows may need one Web Store click.

Queries default to headless and first try a read-only export of the requested site’s cookies from an existing connected local browser. No source browser is changed, no full Chrome profile is cloned, and no password/keychain is accessed. If no connected source is available, use saved Reach state. Multiple possible accounts require browser profiles/use selection. Only missing/expired login needs the human in a visible Reach window; the next query returns to headless with the same profile. Login is periodically saved without requiring the user to close the window. Human page interactions and Reach calls reset the idle timer. The Bridge is supervised with the browser; existing user-owned Bridge processes are preserved, and version conflicts are reported without restarting them.

If login is still needed, `agent-reach login CHANNEL` opens the shared dedicated browser. The user logs in there; for native tools, follow the returned sync instruction. `agent-reach execute CHANNEL ACTION --params '{...}'` prepares and executes the actual task once. If it returns `operation_id`, use `agent-reach resume OPERATION_ID` after the user finishes login. No additional model key is required.

Removing a browser channel clears only that site's login/storage in the dedicated browser and its native session. Other sites are retained. If required cleanup fails, the channel remains registered and the error is returned. Xiaoyuzhou remains optional and needs a Groq key for transcription.

Problems: [troubleshooting.md](troubleshooting.md).
