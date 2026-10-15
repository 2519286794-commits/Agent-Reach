# Update Agent Reach

## 1.6 and later

```bash
agent-reach update
```

One command does everything:

- upgrades the program to the latest GitHub release (`uv tool install --force <release zip>`)
- moves the tools of your added channels to the versions pinned by that release
- refreshes the Agent Reach skill (the one real copy, and the links that let your other AIs read it)

Only want to know if there is a new version? `agent-reach update --check`.

Afterwards, `agent-reach check --text` confirms your channels still work.

If the upgrade step fails, the error `hint` holds the exact command to run by hand. Installed some other way than uv? The hint says to reinstall once with uv, as below.

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
agent-reach login <channel> --import-existing
```

Browser-login channels (xiaohongshu, reddit, twitter, ...) no longer use your own browser's cookies. Run `agent-reach browser setup` and log in again in the Agent Reach browser with `agent-reach login <channel>`.
