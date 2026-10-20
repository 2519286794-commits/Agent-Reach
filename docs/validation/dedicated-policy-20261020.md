# Dedicated browser policy audit — 2026-10-20

Candidate only. PR #815 remains a draft against `release/1.6`. No merge, tag or official release. Package version remains 1.6.0. The earlier 63c272a claim of complete acceptance was too broad.

## Review findings and fixes

All five concrete code defects were confirmed. The changes below distinguish regression coverage from live business acceptance.

| Finding | Final change | Evidence |
|---|---|---|
| BOSS detail used native HTTP authentication | `boss read` now invokes the official OpenCLI `boss detail` browser adapter, pinned to the shared dedicated profile. Native BOSS helper handles browser search only. | Route/parameter regression passed. **Real JD acceptance still pending** after the earlier platform block; no repeated risk requests. |
| Removal reported success after login cleanup failed | Required browser cleanup runs before channel/task/tool deregistration. Failure propagates; the channel remains registered. | Failure injection passed; real synthetic site cleanup passed. |
| www/subdomain storage was missed | Capture open and previously visited origins, include www/cookie origins, clear selected site data and verify remaining cookies. | Regression passed; real local subdomain localStorage/cookie cleared, another site cookie retained. This does not claim discovery of every historical origin from older builds. |
| BOSS archive source caused repeated installation | Accept the installed archive URL or the exact expected VCS commit; repeated prepare reuses it. | Two ensure calls caused zero installs in provenance regression. |
| XHS error hint pointed to personal Chrome | Hint now opens Reach login; all personal-browser export/import commands and source flags removed. | Retired-source commands fail before credential/browser access. |

## Eight-rule implementation

- Work stayed on a feature branch. PR stays draft; release workflow now requires real per-action evidence for the exact source digest. Unit tests and doctor cannot satisfy the gate.
- No maintainer account, credential, absolute home path, browser profile, binary or local API/research prototype is included in the candidate.
- Official OpenCLI 1.8.7 was compared with its npm archive: **2,340 published files matched; no extra non-dependency files**. No upstream source edits.
- Authentication is completed by the human in one dedicated Reach profile. Only already-saved dedicated state is reused. Personal Chrome cookies/files are never imported.
- Ordinary commands no longer launch detached update checks. Existing tools/extensions are reused; an explicit update or allow-upgrade is required to change installed versions.
- Cursor/other application MCP configuration is never changed. A retired entry recorded by old Reach is reported as a manual action only.
- Created artifacts are recorded. Deletion uses this ledger or existing owned-tool records. Unknown files, unrecorded sessions and extra Skill notes survive. If the browser cannot close, uninstall stops before deleting files.
- The user approved an official OpenCLI Bridge companion. The watcher starts/reaps its own child; a failed owned Bridge closes the browser. An existing compatible user Bridge is borrowed, never killed. If another browser adopts our child, it is retained with a visible status note. Incompatible existing versions are left unchanged.

## Browser lifetime

- Login cookies are periodically saved; closing the window is not required to save them.
- Trusted page clicks, keyboard input, scrolling and touch, plus Reach calls, reset idle closure. Script-generated input does not. Browser toolbar activity outside the page is not measured.
- Real accelerated lifecycle test: 6-second idle closed the browser and watcher. Production default remains **600 seconds**. Existing user-owned Bridge PID was preserved.
- Shared profile, automatic extension, Chrome fallback and on-demand reopening remain. Windows execution is **not accepted in this round**.

## Real console acceptance

All rows below came from `python -m agent_reach.cli`, including saved proxy/PATH preparation. A preliminary in-process probe skipped that preparation and produced YouTube/V2EX errors; it is excluded from release evidence.

| Channel | Action | Backend | Items | ms |
|---|---|---|---:|---:|
| github | search | gh | 2 | 1859 |
| youtube | search | yt-dlp | 2 | 5435 |
| bilibili | search | bili-cli | 2 | 1048 |
| v2ex | hot | v2ex-api | 3 | 1539 |
| web | search | exa | 2 | 1588 |
| xiaohongshu | search | opencli | 2 | 5123 |
| xiaohongshu | read | opencli | 1 | 8755 |
| xiaohongshu | comments | opencli | 24 | 9282 |

XHS comments are the records actually loaded by upstream, including replies; this is not a complete-comment export guarantee.
**8 of 40 declared actions accepted on macOS. 32 remain without current candidate acceptance.** BOSS requires human verification before another business request. Other platforms/actions need their own acceptance; no status/installation/old success is promoted to a new pass.

## Quality and distribution

- 399 unit/regression tests passed; Ruff passed; Mypy checked 47 source files. Tests include failure retention, www/observed subdomains, archive reuse, BOSS browser detail routing, unknown-file preservation, trusted activity, Bridge ownership and source-bound release evidence.
- `scripts/check_release_acceptance.py` intentionally fails for this manifest until all missing actions are truly accepted. A v* tag therefore cannot publish this candidate through the release workflow.
- Formal stable installation points to the verified v1.5.0 release and its instructions. This unpublished 1.6.0 candidate uses its supplied wheel; it never points users at an absent v1.6.0 tag. Ordinary installed users may explicitly run update.
- Xiaoyuzhou remains present. ask/Reach MCP/custom Cloak site scraping/OpenCLI patching remain removed.
- Archive and wheel are built only from reviewed Git files. Installed Skill files are generated from that source, not copied from a maintainer-specific working profile.

Source digest: `35c255b6b581976e90b7aafc93236e12a81b5d6d7899d20e646ae082c06fda1c`. Sanitized machine-readable evidence: [release-acceptance.json](release-acceptance.json).
