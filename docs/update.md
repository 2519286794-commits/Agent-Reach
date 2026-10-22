# Update Agent Reach

## 1.6 and later

```bash
agent-reach update
```

One command does everything:

- upgrades the program to the latest GitHub release (`uv tool install --force <release zip>`)
- reinstalls the tools of every added channel, even when Agent Reach itself has no new release: tools with a tested version stay at that version, other tools get the newest version inside their supported range (known-bad versions are skipped); tools no channel uses any more are removed
- refreshes the Agent Reach skill (the one real copy, and the links that let your other AIs read it)

Default channels you removed stay removed; `agent-reach add <channel>` brings one back.

`result.user_actions` lists, in plain sentences, anything the user must do afterwards (e.g. a channel now needs a login). Tell the user each one.

Only want to know if there is a new version? `agent-reach update --check`. Agent Reach also checks by itself at most once a day in the background; when a newer version exists, every command's JSON carries `meta.update` with the version and its release notes.

Afterwards, `agent-reach check --text` confirms your channels still work.

If the upgrade step fails, the error `hint` holds the exact command to run by hand. Installed some other way than uv? The hint says to reinstall once with uv, as below.

## Roll back

A new version misbehaves? Go back to the previous one (replace `<previous>` with its number, e.g. `1.6.0`):

```bash
uv tool install --force https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v<previous>.zip
agent-reach update --sync-only
```

`--sync-only` brings the channel tools and the skill in line with the installed version without upgrading the program again. Channels, keys and logins under `~/.agent-reach/` are kept.

## Coming from 1.5 or earlier

Older versions installed differently, so reinstall once with the same command as [install.md](install.md) (no `uv` yet? see step 0 there):

```bash
uv tool install --force https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v1.6.0.zip
agent-reach setup
```

`agent-reach setup` migrates the old install:

- keys in `~/.agent-reach/config.yaml` stay as they are
- `result.migration.suggested_channels` lists channels you used before; add them again with `agent-reach add <channel>`
- tools the old version installed globally are not removed; Agent Reach 1.6 uses its own private copies
- old CLI logins (bilibili, boss) can be copied over instead of logging in again:

```bash
agent-reach login <channel> # Browser channels: user logs in in the dedicated Reach window
```

Browser-login channels (xiaohongshu, reddit, twitter, ...) no longer use your own browser's cookies. Add them again with `agent-reach add <channel>` (it sets up the Agent Reach browser by itself), then log in there with `agent-reach login <channel>`.
