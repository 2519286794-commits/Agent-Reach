# Shared browser acceptance — 2026-10-20

Candidate: **1.6.0**, targeting `release/1.6`. This record separates implementation checks from actual platform access. It does not certify every platform or Windows browser operation.

## Requested scope

| Item | Result | Evidence / limit |
|---|---|---|
| Remove model planner | Done | No `ask` command or `runtime/ask.py`; no model key required. |
| Remove Reach MCP | Done | No server, registration or MCP entry. `setup` removes an old Cursor entry only if its recorded ownership and unchanged contents match. Foreign entries remain. |
| Remove custom website extraction | Done | Per-site Cloak workers/selectors/API adapters removed. OpenCLI handles browser extraction; BOSS calls its upstream SDK. Normalizing upstream results and existing public/native channels remain. |
| Remove OpenCLI source patches | Done | Patch command/module removed. Installed official 1.8.7 release: **190 shipped JS/JSON files** match the npm tarball byte for byte. |
| One dedicated browser | Passed locally | Shared `~/.agent-reach/browser/profile`; CloakBrowser launched by the existing watcher with OpenCLI extension 1.0.26 loaded automatically. No per-channel browser contexts. |
| Ten idle minutes / automatic reopen | Passed with shortened live timer | Default is 600 seconds. Live test used 3 seconds: browser closed, watcher exited successfully; next call reopened and connected. The test did not wait ten wall-clock minutes. |
| Chrome fallback | Unit-tested | Installation/download failure selects installed Chrome and remembers the fallback. `browser setup --retry-cloak` retries Cloak. No live network failure was deliberately induced. |
| Login inheritance | Passed locally | Explicit one-time import of Xiaohongshu cookies from the user-selected leetengx Bridge profile; source unchanged; subsequent search returned a result. No personal Chrome Cookie database access. |
| Preserve login on reopen | Passed locally | Session cookie survived close/reopen; Xiaohongshu and BOSS cookie counts remained 16 and 12. Cookie presence alone does not prove platform authentication. Private snapshot mode: 0600. |
| BOSS shares browser | Wiring done; business check blocked | Native CLI uses the owned CDP endpoint. Actual search returned **PLATFORM_BLOCKED**. Stopped immediately without backend/account retries; search and JD remain for manual verification. |
| Browser channel dependencies | Unit-tested; Xiaohongshu add exercised locally | Node, OpenCLI, browser and extension prepared by add. BOSS adds its native CLI too. Cloak download failure can use installed Chrome. |
| Site-only cleanup | Passed locally + regression tests | Synthetic site cookie removed while another site's cookie survived. Selected-site tabs/storage are cleared; other sites and source Chrome remain. Logout also deletes old per-site snapshots to prevent login revival. |
| Version / Xiaoyuzhou | Done | Both package versions are 1.6.0; Xiaoyuzhou channel and transcription script restored. Groq key and quota are required; no live transcription check. |
| Official install / update docs | Done | `docs/install.md` uses the official v1.6.0 archive; existing installs use `agent-reach update`. The candidate must be tested from its own wheel before upstream release. |
| Prepare / reopen tests | Restored and adapted | Cloak preference, automatic preparation/rebinding, lost connection, shared profile, idle close, fallback, ownership guard and removal are covered. |

## Live Xiaohongshu results

All website extraction used **unmodified official OpenCLI 1.8.7** in the shared Cloak browser.

- Search `VLA`: 2 items; another search after explicit Chrome import returned 1 item.
- Read one note: 1 item, 22 characters of text. This is the note's text description; it does not interpret its pictures/video.
- Read comments: 20 loaded comment/reply records, 456 text characters. This does not establish a complete comment tree. An upstream limit can include loaded replies.

Official 1.8.8 failed the Xiaohongshu default-filter path with `UPSTREAM_BROKEN`. The previous local installation had three changes: a longer wait, skipping default filters and choosing the first duplicate option. All were removed. New installations use tested 1.8.7; 1.8.8 is excluded. **OpenCLI 2.x business access is unverified here.** An incompatible user-owned singleton requires explicit `--allow-upgrade` before replacement.

## Lifecycle corrections found during acceptance

- Cloak's private interpreter does not import the main program's Config/PyYAML. The launcher passes only the necessary runtime settings.
- The browser proxy bypasses localhost so the OpenCLI extension can reach its local Bridge daemon.
- A previous Reach-owned Chrome profile crashed Cloak locally. It is preserved as a private `profile-before-cloak-*` backup; the shared profile restores Reach's saved cookies. No personal Chrome profile is moved.
- The watcher saves session cookies every two seconds and before normal shutdown. Login persistence no longer depends on the user closing the window.
- Closing one site tab does not terminate the watcher. A shared action lock serializes browser channels; a session lock prevents stale saves racing logout.
- Old Reach-owned per-site snapshots merge once, only filling missing cookies. Logout/removal cannot automatically restore those old credentials.
- Windows npm `.cmd` and POSIX package layouts are covered for explicit Bridge import. Windows browser launch/import still needs a separate live acceptance run.

## Validation

- Core tests: **384 passed** on local macOS.
- The curated source checkout also passed all 384 tests, with local API/research files excluded.
- Ruff: passed. Mypy: passed, 46 source files.
- Wheel gate passed: 57 entries, about 148 KiB; Skill references and Xiaoyuzhou present, removed modules and browser binaries absent. Clean-venv smoke test confirmed 14 channels and rejection of the four retired command entries.
- Installed the candidate wheel locally, ran setup successfully (5/5 defaults), refreshed the installed Skill and confirmed no retired Reach MCP configuration/process. An actual Xiaohongshu search through the installed wheel returned one item in 7.48 seconds.
- Packaging uses reviewed source files only. Local API prototypes, provider research, account data, browser profiles and downloaded binaries are excluded.

## User acceptance

1. Say “去小红书搜 VLA，再看一篇笔记和评论”. Reuse the shared saved login; do not request a model key.
2. Close the Reach browser and repeat a search. It should reopen with the same profile.
3. Handle the BOSS verification manually in the dedicated browser, then run one search; verify JD separately. This is the outstanding platform check.
4. On a second Windows/Mac machine, install this candidate wheel, run setup, add a browser channel, log in or explicitly import one site, then verify the actual action.

No application, message, post, comment or other platform write was performed during this acceptance.
