---
name: agent-reach
description: >
  Use when the user names a supported platform, shares its URL, or asks to configure or diagnose its channel:
  小红书/xiaohongshu, B站/bilibili, Twitter/X, Reddit, Facebook, Instagram,
  YouTube (subtitles, transcripts), V2EX, 雪球/股票行情, GitHub,
  LinkedIn/Boss直聘 jobs,
  or when your built-in web search / fetch is missing or fails.
  Supplement existing agent capabilities: prefer available public web tools for public content on any platform.
  Use Reach when evidence is insufficient, tools are unavailable, or a declared structured action is needed.
  Read-only: never post, comment, like, or log in on the user's behalf.
metadata:
  homepage: https://github.com/Panniantong/Agent-Reach
  version: "{{VERSION}}"
---

# Agent Reach

一个命令接所有平台：`agent-reach`。只读，默认输出 JSON；`setup --text` 直接显示安装能力表。

## 安装完成展示精简能力表

安装或重新初始化后，最终回复直接展示 `result.installation_report.markdown`：按安装电脑本地时间生成的问候、默认安装结果、图标说明、一张“平台 / 不登录可以查什么 / 需要登录后再试”的三列表、一句实测状态。不要自行补另一句问候，也不要再补详细矩阵或后台动作清单；详细边界仅在用户追问时读取 [能力边界](references/capabilities.md)。

运行 `agent-reach setup` 获取 JSON；用户操作终端可用 `agent-reach setup --text`。报告链接只作补充。保留安装失败、用户移除和需处理的状态。✅ 表示不用登录可先查的内容；❌ 只标明所列 Reach 功能需要登录后再试，登录不保证访问成功；— 表示这里没有额外的登录功能。Reddit 的公开帖子、正文和公开评论先用现有网页工具，不要求登录，也不承诺读全评论。

问候由程序读取本地时钟：05–10 点早上、11–13 点中午、14–17 点下午、18–21 点晚上，其余为深夜；不联网定位、不询问时区。表中写清内容类型，如“搜摘要”“读正文”“读详情”，避免“页面提示登录时”“更多站内功能”“部分推文”等含糊说法。网络失败、尚未实测、未支持的功能不能标成 ❌ 要求用户登录。如果当前运行时没有 `installation_report`，核对所装版本和来源。

表格功能项尽量用 2–3 字短语，如“读正文、看评论”“看热帖、看热股”。短语保留内容区别：摘要和链接不写成全文，热门股票不写成“牛股”；评论范围、字幕来源的共同说明只在表下写一次。

## 怎么用

按所需内容选择入口，所有平台适用：

1. **公开信息**：有链接先用已有网页工具打开；找内容先用已有搜索工具，按需加 `site:平台域名`。正文、评论、字幕分别检查是否已满足请求。已有结果足够就直接回答，不准备渠道或登录。
2. **补充能力**：公开结果缺少用户需要的部分、现有工具不可用，或用户要求 Reach 已声明的结构化/站内动作时，再查 `agent-reach channels`，调用对应动作。已有免登录原生工具或公开接口可直接复用；不要求每个任务先重复做一次网页搜索。网页工具不可用时，Reach `web search` / `web read` 提供匿名保底。
3. **按需认证**：仅当尚未满足的任务所选路径确实要求登录时，再加载 [会话配置](references/sessions.md)，复用已授权会话或请用户本人登录。没有配置浏览器说明需要配置；403、验证码、DNS/TLS 错误、限流、超时按各自原因处理。正文旁的登录按钮不算登录墙。
4. **交付已有结果**：保留公开结果，说明缺少正文、哪些评论或字幕；登录仅服务于剩余缺口。用户跳过登录也能拿到已读取的内容。评论计数、字幕轨道清单、页面壳、搜索摘要分别标注，不当成评论正文、字幕正文或完整文章。

平台名称和 URL 用来识别来源，不自动触发安装、`ensure` 或登录。用户要求安装、登录、导入或退出时读会话配置；故障、升级或卸载时读 [维护说明](references/maintenance.md)，查询时按需加载。

Reddit 公开帖可搜索 `site:reddit.com 关键词` 再打开原帖，公开 JSON 有时包含评论父子 ID；以本次实际返回为准。YouTube/B站简介与字幕、视频内容分别验收；X 的单帖公开内容与评论流分别验收。某台机器的失败不能推广为平台必须登录，也不固化“某平台总能匿名读全”。网络路径不同的结果分别记录。

需要 Reach 执行的一句话请求，优先调用 MCP 的 `reach_execute`；CLI 环境可用 `agent-reach ask "用户原话"`，由已配置的模型选动作并总结。渠道未准备好时，执行入口会返回 `required_action` 与 `operation_id`；用户完成登录后调用 `reach_resume` 或 `agent-reach resume OPERATION_ID`。不要自行拼安装、导入、重试的命令链。

```bash
agent-reach channels                      # 每个渠道有哪些动作、要什么参数（不确定就先跑这个）
agent-reach ask "去小红书找数据平台笔记并总结" # 已配置模型时的一句话入口
agent-reach ensure <渠道>                 # 安装、复用授权会话并实测
agent-reach <渠道> <动作> [参数]          # 例：agent-reach xiaohongshu search "咖啡" --limit 5
agent-reach read <链接>                   # 给链接，自动认出渠道
```

结果：

- `ok: true` → 内容在 `items` 里，每条有 `title / url / author / published_at / text`，原始数据在 `raw`。
- `ok: false` → 看 `error.code`，按 `error.hint` 做：

| error.code | 怎么办 |
|---|---|
| `NEED_SETUP` | 调用 `reach_ensure` 或 `agent-reach ensure <渠道>`，按结构化结果继续 |
| `NEED_LOGIN` | 保留公开结果；剩余任务仍需要此路径时，由用户本人登录，再用 `operation_id` 调用 `reach_resume` |
| `UPSTREAM_BROKEN` | 这个渠道暂时不可用，告诉用户，不要反复重试 |
| `TIMEOUT` | 看失败阶段与渠道状态，不反复开窗或立即重试 |
| `RATE_LIMITED` | 按 `retry_after_seconds` 等待，程序暂停该渠道 |
| `NOT_FOUND` / `BAD_INPUT` | 检查链接或参数，必要时跑 `agent-reach channels` |

## 规则

1. 所有平台先判断现有公开能力是否满足任务；只为缺口调用 Reach。需要结构化/站内动作时可直接选已声明动作，认证按实际路径决定。
2. 实际调用 Reach 渠道前说一句"用 agent-reach 的 X 渠道"。
3. 多平台调研按会话分组；共用浏览器的命令串行，独立会话可以并行。
4. 只做读取。发帖、评论、点赞一律不做。
5. 禁止隐式提取登录态。用户明确授权后，只导入指定站点的登录态；不得输出 Cookie、Token 或凭据。已有授权无需反复询问。

## 渠道

{{CHANNEL_TABLE}}

表中 `login` 是渠道认证入口，公开内容查询不以登录为前提；不同动作的要求以实际结果为准。`default` 表示默认安装，不保证所有网络环境均可达；调用可选渠道时由 `ensure` 准备。Reddit 的公开网页路径无需添加 Reddit 渠道。默认渠道也可以去掉，去掉后更新不会再加回来。



## 会话复用：先检查，再决定是否需要登录

Cloak 查询和导入验收默认 `headless=True`。独立登录使用 `agent-reach cloak login CHANNEL`：由用户在可视窗口登录，检测成功后自动保存并关闭，再验收查询。此路径不需要 OpenCLI；OpenCLI 使用自己的 Chrome 会话，Cookie 导入仅为可选迁移方式。

登录时只应弹出一个 Cloak 窗口；窗口提示自动保存，普通 Cloak 查询在后台运行并自动关闭窗口。`cloak login` 最多等待 15 分钟；取消或超时会返回对应原因，不能自行反复重开。旧的 `browser setup` 会另开标有 OpenCLI Browser 的专用 Chrome，只有用户明确选择该路径时才执行；它闲置约 10 分钟后关闭。复用用户已有 Chrome 时，不要关闭原窗口。

安装和 `add` 不打开浏览器。`ensure <渠道>` 优先复用已有会话并执行正式验收；显式 `--reuse-profile ID` 授权从该 Chrome 配置导入指定站点的 Cookie，该授权在本机保存，可用 `--forget-source` 撤销。`login <渠道>` 默认只查看现有连接。连接正常或保存过状态不等于当前已登录。

公开能力不足并选定浏览器动作后，后端按动作选择：小红书 search/read/comments、Twitter search、Facebook search、Instagram search/profile/posts 使用 CloakBrowser → OpenCLI；Reddit 浏览器 search 使用 CloakBrowser → OpenCLI，read/subreddit 使用 OpenCLI；BOSS search 使用 CloakBrowser → OpenCLI → boss-agent-cli，BOSS read 仅支持 CloakBrowser；LinkedIn jobs 使用 CloakBrowser → linkedin-mcp。程序记住近期技术故障并暂时跳过该后端；选择与恢复由运行时完成。其他动作以 `agent-reach channels` 中的后端声明为准。具体会话选择见 [会话配置](references/sessions.md)。

小红书 read 仅返回文字描述，不声称理解图片/视频。BOSS 搜索若 salary_encoded=true，不能猜数字；read 职位链接获取详情中的可读薪资。

用户要求小红书评论时使用 `comments` 动作：`agent-reach xiaohongshu comments "完整笔记链接" --limit 20`；MCP 使用 `reach_execute(channel="xiaohongshu", action="comments", params={"target":"完整笔记链接","limit":20})`。保留搜索返回的访问参数。limit 限顶级评论，已加载回复会一并返回；注明页面样本范围。只有评论数量的字段不能当成评论正文。

遇到 PLATFORM_BLOCKED、RATE_LIMITED、NEED_LOGIN、BUSY 就停止本次降级，不换账号或后端反复请求。同一 profile 的 Reach 命令互斥；多渠道共用同一 profile 时串行。

依赖修复和发布升级见 [维护说明](references/maintenance.md)；普通查询不修改依赖。

## 用户要管理 Agent Reach 时

| 用户说 | 你运行 |
|---|---|
| 看看状态 / 哪些能用 | `agent-reach doctor --text`（要实测再跑 `agent-reach check <渠道> --search --text`） |
| 加上某个平台（如"加上小红书"） | `reach_ensure` 或 `agent-reach ensure <渠道>`；需要本人操作时按 `required_action` 提示，再 `resume` |
| 登录过期了 | 先读会话配置；`agent-reach login <渠道>` 默认仅检查，实际登录由用户本人完成 |
| 去掉某个平台 / 退出登录 | `agent-reach remove <渠道>`；Cloak 主后端用 `agent-reach logout <渠道>` 删除 Reach 管理的会话 |
| 升级 / 更新 | 先读 [维护说明](references/maintenance.md)，确认当前安装来源和版本，再执行更新。 |
| 卸载 | 先 `agent-reach uninstall --dry-run` 给用户看，确认后 `agent-reach uninstall` |
| 让另一个 AI 也能用 | `agent-reach skill link <那个 AI 的 skill 目录>`；`agent-reach skill` 查看现在放在哪 |

首次安装按上方“安装完成展示精简能力表”交付；普通查询按需读取 [能力边界](references/capabilities.md)，不预先安装全部可选渠道。

## 有新版本时

任何结果里出现 `meta.update`，就说明有新版本。每次对话只提一次，用用户的语言、大白话：

1. 告诉用户 Agent Reach 有新版本（`meta.update.latest`）。
2. 从 `meta.update.notes` 里挑 1 到 3 个简短要点，说清楚这次改了什么。
3. 问用户要不要更新。

用户同意更新后，先读 [维护说明](references/maintenance.md)，确认安装来源；从相同来源更新，避免将本地构建覆盖为其他版本。更新后说明实际改动和仍需用户完成的操作。

Facebook search 已接入 CloakBrowser → OpenCLI；profile 仍使用 OpenCLI。可用 `cloak login facebook` 独立登录，或显式 `cloak import facebook --opencli-profile ID` 迁移站点 Cookie。
