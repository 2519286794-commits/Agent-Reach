# Changelog / 更新日志

All notable changes to this project will be documented in this file.

本项目的所有重要变更都会记录在此文件中。

---

## [1.6.0] - unreleased

中文：

- 加一个平台只要一句话，需要的软件（Node.js、Chrome、ffmpeg、浏览器扩展）都会自动装好，不需要管理员密码；你只需要登录或者填一个 Key。
- 默认平台也能去掉，去掉后更新不会再加回来；去掉时会一起清掉它的登录和专用工具。
- 更新会把各平台用到的工具升到最新版；有新版本时，AI 会用大白话告诉你改了什么，你同意了才更新。
- 登录不再读你自己浏览器的 Cookie，而是在 Agent Reach 专用浏览器里由你本人登录。

English:

- Adding a platform takes one sentence. Whatever it needs (Node.js, Chrome, ffmpeg, the browser extension) is installed for you, with no admin password; you only log in or enter a key.
- Default platforms can be removed, and updates won't add them back; removing one also clears its login and private tools.
- Updating also moves each platform's tools to their latest versions. When a new version is out, your AI tells you in plain words what changed and updates only if you say yes.
- Logins no longer read your own browser's cookies; you log in yourself in the dedicated Agent Reach browser.

1.6 is a rebuild. Agents call one command, `agent-reach`; everything Agent Reach installs or stores lives under `~/.agent-reach/`.
1.6 是重构版本：Agent 只调一个命令 `agent-reach`，Agent Reach 装的、存的东西全部在 `~/.agent-reach/` 下。

### ✨ New / 新增

- **Unified entry / 统一入口**: `agent-reach <channel> <action>`, `agent-reach read <url>`, `agent-reach channels`. One JSON envelope per call, unified error codes with hints, per-call timeout, automatic fallback to the next backend.
- **Management / 管理命令**: `setup`, `add` / `remove <channel>`, `login` / `logout <channel>`, `doctor`, `check`, `skill`, `skill link <dir>`, `update`, `configure`, `uninstall`.
- **One-step setup / 一步装好**: `setup` adds every default channel through the same path as `add` (bili-cli goes into `~/.agent-reach/tools/`) and reports what works, which AIs can read the skill, optional channels and optional logins. / `setup` 用和 `add` 同一套逻辑开启全部默认渠道，并汇报哪些能用、哪些 AI 能读到 skill、可选渠道和可选登录。
- **Skill placement / skill 放置**: one real copy at `~/.agents/skills/agent-reach/SKILL.md` (read directly by Codex, OpenCode, Cline, Warp, Zed); a link to it in the skill folder of Claude Code, OpenClaw, Hermes, Cursor, Gemini CLI, GitHub Copilot and Windsurf when installed (a copy where links are not allowed, e.g. Windows). `agent-reach skill link <dir>` covers any other AI. / 只放一份真文件，其他 AI 的 skill 目录里放指向它的链接（链接：一个指向原文件的快捷方式）。
- **Private upstream installs, latest allowed version / 上游私有安装，用最新可用版本**: tools go into `~/.agent-reach/tools/`; the user's own copies are untouched. Versions are not pinned: each tool installs its latest version, limited only by an optional `floor` (minimum) and `exclude` (known-bad versions shipped in a release). `state.json` records the version actually installed and `doctor` shows it. Single-instance tools (OpenCLI) reuse the user's copy; if it is older than the floor, it is upgraded only with `--allow-upgrade`. / 工具不锁版本，装最新可用版；已知有问题的版本在新版本里排除；doctor 显示实际版本。
- **`add` gives a finished result / `add` 一步到位**: missing prerequisites are installed without an admin password: uv (official script), ffmpeg (`imageio-ffmpeg` in a private venv), Node.js (official release under `~/.agent-reach/tools/node/` when the system has none), Chrome (system Chrome, else Chrome for Testing under `~/.agent-reach/tools/chrome/`). git is no longer needed (Boss installs from a GitHub archive). The user only logs in or enters a key. / 缺的依赖自动装好，用户只需登录或填 Key。
- **Login state under `~/.agent-reach/` / 登录状态统一管理**: CLI tool logins in `sessions/`, browser logins in a dedicated Agent Reach browser. The browser opens by itself when a channel needs it and closes after 10 minutes without use. On macOS and Linux the OpenCLI extension is loaded automatically on every launch (no click); on Windows the user clicks "Add to Chrome" once. Agent Reach never logs in for the user and never reads the user's own browser cookies. / 专用浏览器按需自动打开，10 分钟不用自动关闭；macOS/Linux 自动装好扩展。
- **remove cleans up / 去掉渠道会清理干净**: deletes the channel's private tools nobody else uses, its CLI session, its login keys and its site cookies in the Agent Reach browser. When no browser-login channel is left, the Agent Reach browser folder is deleted and OpenCLI is uninstalled if Agent Reach installed it.
- **Removable default channels / 默认渠道可去掉**: `state.json` records `removed_defaults`; `setup` and `update` never add them back; `add` brings one back.
- **doctor states / 体检**: not_added, needs_setup, needs_login, unverified, ready, broken; plus `regressed` per channel (passed in the previous check, fails in the latest).
- **update** runs `uv tool install --force` on the latest release, upgrades every added channel's tools to the latest allowed version (also when Agent Reach itself has no new release), prunes tools no added channel uses, drops channels no longer in the registry, and refreshes the skill. `result.user_actions` lists in plain sentences what the user must do afterwards. Rollback: `uv tool install --force <previous release zip>`, then `agent-reach update --sync-only`. uv is the only supported installer. 1.5 and earlier installs are migrated on first `setup` / `update`; `config.yaml` keys are kept.
- **Update notice / 新版本提醒**: at most once per 24 h, any command except `update` starts a short background check of the latest GitHub release (never waits on the network; offline is silent). When a newer version exists, every JSON envelope carries `meta.update = {current, latest, notes}`; the skill tells the AI to explain the notes to the user and update only with their yes. / 有新版本时 AI 用大白话告诉用户，用户同意才更新。
- **Release notes / 发布说明**: every CHANGELOG version section starts with a plain summary for users in Chinese and English; it becomes the GitHub release body the AI shows users.
- Xueqiu quotes and stock search via Tencent public quotes (no login); Xueqiu community data uses a session the user imports with `agent-reach login xueqiu --sync`.
- YouTube `transcribe`; LinkedIn uses its own MCP registration in `~/.agent-reach/mcporter.json`.

### 🔄 Changed / 变更

- Default channels: web (fallback only), YouTube, GitHub, V2EX, B站. Optional: 小红书, Reddit, LinkedIn, Boss直聘, 小宇宙, 雪球. Experimental: Twitter, Facebook, Instagram.
- The agent skill is generated from the channel list and replaced on every update.

### 🗑️ Removed / 移除

- RSS channel (agents read feeds themselves).
- xhs-cli, rdt-cli, twitter-cli backends: they read browser cookies by themselves.
- `configure --from-browser`, `twitter-cookies`, `xhs-cookies`, the old `install --channels`, the old `skill --install`, `format`, `check-update`, MCP server entry.
- `watch` (use `doctor`, which now reports `regressed`), `doctor --live` (use `check`), `browser start` (the browser opens by itself), pipx installs.

### 🐛 Bug Fixes / 修复

#### 🔐 Boss直聘 — 登录态误判（双凭据存储）

- **根因：** Boss 有两个互不代表的登录态存储——本地 `~/.boss-agent/auth/session.enc`
  和专用 Chrome profile 内的浏览器 cookie。`boss status` / `status --live` **只校验前者**
  （Bridge/httpx 时代的遗留凭据库），而 `existing-browser` 严格 CDP 模式下搜索走的是浏览器 cookie。
  「本地有旧凭据 + 浏览器未登录」时 `boss status` 会报 `logged_in: true`，误导 Agent
  跳过登录直接搜索，最终撞上 `AUTH_EXPIRED`；旧 runbook 又禁止把 `_security_check`
  当成未登录，两条规则叠加把 Agent 推向「反爬滑块」的错误分支。
- **修复：** `check()` 新增第 4 层只读探测 `_cdp_zhipin_login_cookie()`，用纯标准库
  实现的最小 WebSocket 客户端直接问 CDP 浏览器本体（`Storage.getCookies`）有无 zhipin
  的 `wt2` cookie，**以浏览器为准**，不引入新依赖、不拉起浏览器、不执行搜索。
  无 wt2 → 明确报「浏览器未登录，搜索会报 AUTH_EXPIRED」并指向「用户登录 +
  `login --cdp`」；探测失败 → 报「登录态未知」；安全校验页提示也附带浏览器 cookie 状态。
- **Runbook 修正：** 删除误导规则「判断登录态只信 `boss status`」，改为以 doctor 的
  浏览器 cookie 探测为准；拉起专用 Chrome 后**强制暂停让用户肉眼确认**登录状态；
  `AUTH_EXPIRED` 定为 ground truth（直接走登录流程，禁止往安全校验方向解释），
  `_security_check` 仅在无 `AUTH_EXPIRED` 时按滑块处理。

### ✨ Features / 新增

#### 🎯 Boss直聘 channel

- 新增 `boss` channel：经 boss-agent-cli + CDP 真 Chrome 搜岗位、取 JD 全文。
- `check()` 四层只读探测（boss-agent-cli 装没装 → 9222 端口通不通 → 有无 zhipin 页签
  → 浏览器内有无 `wt2` 登录 cookie）。
- 抓取走公开 API（`search_jobs` + `job_card_browser` + `browser_source="existing-browser"`）。
- `agent-reach install --system --channels=boss` 可安装锁定上游 boss-agent-cli
  （#403–#407 已合并入 master）固定提交的后端；上游发布正式版后切回版本约束。
- Skill 与安装指南支持“帮我配 Boss直聘”：Agent 启动仅监听回环地址的专用 Chrome，
  用户只负责手动登录，最后由 Agent 验证登录态与 CDP 链路。
- 固定依赖从 fork 快照 `8ff6bd3` 切换到上游 commit `4c991b7`（#403–#407 已合并入
  master）：已登录 CDP 会话可直接复用，搜索可通过 `--browser-source existing-browser`
  禁止 headless 降级。
- code 37 按原始文案分类：环境异常为 `ENVIRONMENT_RISK` 并立即停止；只有明确
  token/stoken 过期才允许一次刷新。专用 Chrome profile 应长期复用并降低频率。

## [1.3.1] - 2026-03-27

### 🐛 Bug Fixes / 修复

#### 📈 Xueqiu (雪球) — 全面修复

- **修复 400 错误根本原因：** `_ensure_cookies()` 仅访问首页只能获取 `acw_tc`（防 DDoS token），`xq_a_token` 由雪球前端 JS 动态生成，无法通过纯 HTTP 请求获取。新增三级 cookie 加载策略：① 读取 config 文件（`--from-browser` 保存的）→ ② 自动从本地 Chrome 浏览器提取（需安装 browser-cookie3）→ ③ homepage fallback
- **修复 User-Agent：** `"agent-reach/1.0"` 被雪球反爬系统识别拒绝，改为真实 Chrome UA
- **修复缺失 `Referer` 头：** 所有 API 请求加上 `Referer: https://xueqiu.com/`
- **修复 `get_hot_posts()` 端点：** 原端点 `/statuses/hot/listV3.json` 已废弃（返回空 body），改为 `/v4/statuses/public_timeline_by_category.json`，正确解析 `item.data` JSON 字符串获取 author/likes/text
- **修复 `urllib.request.quote` → `urllib.parse.quote`：** 明确使用正确模块
- **修复 `configure --from-browser` 不提取雪球 Cookie：** `PLATFORM_SPECS` 加入 Xueqiu，检测 `xq_a_token` 存在才保存
- **修正文档误导：** README/SKILL.md 中"无需配置"/"public API, no login required" → 准确描述需要 browser cookie
- **改善错误信息：** `check()` 失败时提示 `configure --from-browser chrome` 而非"可能需要代理"

---

## [1.3.0] - 2026-03-12

### 🆕 New Channels / 新增渠道

#### 💻 V2EX
- Hot topics, node topics, topic detail + replies, user profile via public JSON API
- Zero config — no auth, no proxy, no API key required
- `get_hot_topics(limit)`, `get_node_topics(node_name, limit)`, `get_topic(id)`, `get_user(username)`
- 通过公开 JSON API 获取热门帖子、节点帖子、帖子详情+回复、用户信息
- 零配置，无需认证、无需代理、无需 API Key

### 📈 Improvements / 改进

- Channel count: 14 → 15
- 渠道数量：14 → 15

---

## [1.1.0] - 2025-02-25

### 🆕 New Channels / 新增渠道

#### ~~📷 Instagram~~ (removed — upstream blocked)
- ~~Read public posts and profiles via [instaloader](https://github.com/instaloader/instaloader)~~
- **Removed:** Instagram's aggressive anti-scraping measures broke all available open-source tools (instaloader, etc.). See [instaloader#2585](https://github.com/instaloader/instaloader/issues/2585). Will re-add when upstream recovers.
- **已移除：** Instagram 反爬封杀导致所有开源工具（instaloader 等）失效。上游恢复后会重新加回。

#### 💼 LinkedIn
- Read person profiles, company pages, and job details via [linkedin-scraper-mcp](https://github.com/stickerdaniel/linkedin-mcp-server)
- Search people and jobs via MCP, with Exa fallback
- Fallback to Jina Reader when MCP is not configured
- 通过 linkedin-scraper-mcp 读取个人 Profile、公司页面、职位详情
- 通过 MCP 搜索人才和职位，Exa 兜底
- 未配置 MCP 时自动 fallback 到 Jina Reader

#### 🏢 Boss直聘
- QR code login via [mcp-bosszp](https://github.com/mucsbr/mcp-bosszp)
- Job search and recruiter greeting via MCP
- Fallback to Jina Reader for reading job pages
- 通过 mcp-bosszp 扫码登录
- MCP 搜索职位、向 HR 打招呼
- Jina Reader 兜底读取职位页面

### 📈 Improvements / 改进

- Channel count: 9 → 12
- `agent-reach doctor` now detects all 12 channels
- CLI: added `search-linkedin`, `search-bosszhipin` subcommands
- Updated install guide with setup instructions for new channels
- 渠道数量：9 → 11
- `agent-reach doctor` 现在检测全部 11 个渠道
- CLI：新增 `search-linkedin`、`search-bosszhipin` 子命令
- 安装指南新增渠道配置说明

---

## [1.0.0] - 2025-02-24

### 🎉 Initial Release / 首次发布

- 9 channels: Web, Twitter/X, YouTube, Bilibili, GitHub, Reddit, XiaoHongShu, RSS, Exa Search
- CLI with `read`, `search`, `doctor`, `install` commands
- Unified channel interface — each platform is a single pluggable Python file
- Auto-detection of local vs server environments
- Built-in diagnostics via `agent-reach doctor`
- Skill registration for Claude Code / OpenClaw / Cursor
- 9 个渠道：网页、Twitter/X、YouTube、B站、GitHub、Reddit、小红书、RSS、Exa 搜索
- CLI 支持 `read`、`search`、`doctor`、`install` 命令
- 统一渠道接口 — 每个平台一个独立可插拔的 Python 文件
- 自动检测本地/服务器环境
- 内置诊断 `agent-reach doctor`
- Skill 注册支持 Claude Code / OpenClaw / Cursor
