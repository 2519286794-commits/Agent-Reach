# Shared dedicated browser

CloakBrowser supplies the browser, and OpenCLI/boss-agent-cli supply website extraction. Reach owns one profile at `~/.agent-reach/browser/profile`, one extension directory, and the existing 600-second idle watcher. There are no per-site Cloak workers or custom DOM/API extraction adapters in Reach.

`add` prepares Node, OpenCLI, the browser and extension. CloakBrowser runs through its public persistent-context launcher in a private tool environment. Its binaries are cached under `~/.agent-reach/cloak-binaries`; installation/download failure falls back to installed Chrome. The next browser action automatically prepares/reopens the same profile. BOSS uses this browser's CDP endpoint. On Windows the Cloak extension is loaded automatically; a system-Chrome fallback may need Web Store installation.

Cookie inheritance is explicit and site-scoped via `browser import CHANNEL --opencli-profile ID` or `--state-file FILE`. It is a one-time operation. No Chrome cookie database is read, no standing source grant is retained, and import is not authentication acceptance. `remove` clears the selected site's cookies/storage and native session, retaining other sites and the source browser.

Previous Reach-owned per-site snapshots are merged once without replacing newer shared cookies. Logout/removal clears the retired per-site state too. Chrome fallback is remembered; use `agent-reach browser setup --retry-cloak` after fixing the download connection.

This candidate installs official OpenCLI 1.8.7 for a new installation; 1.8.8 is excluded because its unchanged Xiaohongshu default-filter path failed local acceptance. OpenCLI 2.x has not completed business acceptance here. Existing user installations require explicit `--allow-upgrade` before an incompatible copy is replaced. Reach does not edit OpenCLI's source files.

CloakBrowser's wrapper and browser binary have separate licenses; see [upstream binary license](https://github.com/CloakHQ/CloakBrowser/blob/main/BINARY-LICENSE.md). Do not describe the binary as MIT/open-source or promise unrestricted redistribution.

See [install.md](install.md), and the packaged Skill session reference for commands. Local acceptance results are recorded separately from unit-test results.
