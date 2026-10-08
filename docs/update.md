# Update Agent Reach

## 2.0 and later

```bash
agent-reach update
```

One command does everything:

- upgrades the program with the installer you used (uv or pipx) to the latest GitHub release
- moves the tools of your added channels to the versions pinned by that release
- refreshes the Agent Reach skill in your agent's skill folder

Only want to know if there is a new version? `agent-reach update --check`. `agent-reach watch --text` also reports available updates.

Afterwards, `agent-reach check --text` confirms your channels still work.

If the upgrade step fails, the error `hint` holds the exact command to run by hand.

## Coming from a version before 2.0

Older versions installed differently, so reinstall once with the same command as [install.md](install.md):

```bash
uv tool install --force https://github.com/Panniantong/Agent-Reach/archive/refs/tags/v2.0.0.zip
agent-reach setup
```

(pipx: `pipx install --force <same URL>`.)

`agent-reach setup` migrates the old install:

- keys in `~/.agent-reach/config.yaml` stay as they are
- `result.migration.suggested_channels` lists channels you used before; add them again with `agent-reach add <channel>`
- tools the old version installed globally are not removed; Agent Reach 2.0 uses its own private copies
- old CLI logins (bilibili, boss) can be copied over instead of logging in again:

```bash
agent-reach login <channel> --import-existing
```

Browser-login channels (xiaohongshu, reddit, twitter, ...) no longer use your own browser's cookies. Run `agent-reach browser setup` and log in again in the Agent Reach browser with `agent-reach login <channel>`.
