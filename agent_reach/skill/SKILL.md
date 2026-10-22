---
name: agent-reach
description: >
  Use when the user names a supported platform, shares its URL, or asks to configure or diagnose its channel:
  小红书/xiaohongshu, B站/bilibili, Twitter/X, Reddit, Facebook, Instagram,
  YouTube (subtitles, transcripts), 小宇宙/Xiaoyuzhou podcasts, V2EX, 雪球/股票行情, GitHub,
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
3. **按需认证**：仅当尚未满足的任务所选路径确实要求登录时，再加载 [会话配置](references/sessions.md)，先复用本机已有的该站登录和 Reach 保存的会话，失效或缺失时再请用户本人登录。没有配置浏览器说明需要配置；403、验证码、DNS/TLS 错误、限流、超时按各自原因处理。正文旁的登录按钮不算登录墙。
4. **交付已有结果**：保留公开结果，说明缺少正文、哪些评论或字幕；登录仅服务于剩余缺口。用户跳过登录也能拿到已读取的内容。评论计数、字幕轨道清单、页面壳、搜索摘要分别标注，不当成评论正文、字幕正文或完整文章。

平台名称和 URL 用来识别来源，不自动触发安装、`ensure` 或登录。用户要求安装、登录或退出时读会话配置；故障、升级或卸载时读 [维护说明](references/maintenance.md)，查询时按需加载。

CLI 也按此顺序执行：渠道**已经加上**（默认渠道或 `add` 过）时，搜索/阅读直接走这个渠道的站内工具，不先查网页。渠道**还没加**时，带 `public_web` 的搜索/阅读动作先复用 Reach 的免登录网页搜索/读取，成功后直接返回，不准备浏览器。`backend: public-web` 和 `meta.access.scope` 区分搜索结果与页面文字；不保证站内排序、最新状态、全文或全部评论。公开结果不足才尝试站内工具，实际返回 `NEED_LOGIN` 才请用户登录。用 `--backend public-web` 可只查公开网页；需要站内数据时指定该动作声明的 `--backend opencli` 或 `--backend boss-agent-cli`。评论、字幕、账号列表等动作保持原有粒度；Instagram 搜用户不以通用网页搜索冒充。

Reddit 公开帖可搜索 `site:reddit.com 关键词` 再打开原帖，公开 JSON 有时包含评论父子 ID；以本次实际返回为准。YouTube/B站简介与字幕、视频内容分别验收；X 的单帖公开内容与评论流分别验收。某台机器的失败不能推广为平台必须登录，也不固化“某平台总能匿名读全”。网络路径不同的结果分别记录。


```bash
agent-reach channels                      # 每个渠道有哪些动作、要什么参数（不确定就先跑这个）
agent-reach ensure <渠道>                 # 安装、复用专用会话并实测
agent-reach <渠道> <动作> [参数]          # 例：agent-reach xiaohongshu search "咖啡" --limit 5
agent-reach read <链接>                   # 给链接，自动认出渠道
```

结果：

- `ok: true` → 内容在 `items` 里，每条有 `title / url / author / published_at / text`，原始数据在 `raw`。
- `ok: false` → 看 `error.code`，按 `error.hint` 做：

| error.code | 怎么办 |
|---|---|
| `UPSTREAM_BROKEN` | 告诉用户当前故障，可询问是否从原安装来源更新一次；不自动更新、不反复重试 |
| `TIMEOUT` | 看失败阶段与渠道状态，不反复开窗或立即重试 |
| `RATE_LIMITED` | 按 `retry_after_seconds` 等待，程序暂停该渠道 |
| `NOT_FOUND` / `BAD_INPUT` | 检查链接或参数，必要时跑 `agent-reach channels` |

## 规则

1. 所有平台先判断现有公开能力是否满足任务；只为缺口调用 Reach。需要结构化/站内动作时可直接选已声明动作，认证按实际路径决定。
2. 实际调用 Reach 渠道前说一句"用 agent-reach 的 X 渠道"。
3. 多平台调研按会话分组；共用浏览器的命令串行，独立会话可以并行。
4. 只做读取。发帖、评论、点赞一律不做。
5. 优先复用本地已有的站点登录：已连接的浏览器只读导出当前网站 Cookie，原浏览器不变；不得输出凭据。缺失或失效时，才由用户本人登录。

## 渠道

{{CHANNEL_TABLE}}

表中 `login` 是渠道认证入口，公开内容查询不以登录为前提；不同动作的要求以实际结果为准。`default` 表示默认安装，不保证所有网络环境均可达；调用可选渠道时由 `ensure` 准备。Reddit 的公开网页路径无需添加 Reddit 渠道。默认渠道也可以去掉，去掉后更新不会再加回来。



## 会话复用：先检查，再决定是否需要登录



`setup` 安装默认渠道；`add` 为浏览器渠道自动准备共用浏览器和插件。`login <渠道>` 打开该网站，由用户登录。先尝试复用本地浏览器已有的站点登录；程序定期保存，无需关窗。业务访问需要实际验证。


小红书 read 仅返回文字描述，不声称理解图片/视频。BOSS 搜索若 salary_encoded=true，不能猜数字；read 职位链接获取详情中的可读薪资。


遇到 PLATFORM_BLOCKED、RATE_LIMITED、NEED_LOGIN、BUSY 就停止本次降级，不换账号或后端反复请求。同一 profile 的 Reach 命令互斥；多渠道共用同一 profile 时串行。

依赖修复和发布升级见 [维护说明](references/maintenance.md)；普通查询不修改依赖。

## 用户要管理 Agent Reach 时

| 用户说 | 你运行 |
|---|---|
| 加上某个平台 | `agent-reach add <渠道>`，自动准备依赖；需要登录时再请用户本人完成 |
| 看看状态 / 哪些能用 | `agent-reach doctor --text`（要实测再跑 `agent-reach check <渠道> --search --text`） |
| 登录过期了 | 先读会话配置；`agent-reach login <渠道>` 打开共用专用浏览器，由用户本人登录 |
| 去掉某个平台 / 退出登录 | `agent-reach remove <渠道>`；`agent-reach logout <渠道>` 清除专用浏览器中该网站的登录 |
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


## 共用专用浏览器

普通查询默认 headless，不弹窗；`login CHANNEL` 才显窗，下一次查询收回窗口转回无头，始终沿用同一配置。所有浏览器渠道使用 `~/.agent-reach/browser/profile`，CloakBrowser 优先，下载失败回退本机 Chrome。OpenCLI 插件自动准备，网页提取由上游 OpenCLI 或原生 CLI 执行。BOSS 使用同一专用浏览器；不启动额外个人 Chrome。闲置 10 分钟自动关闭，下次调用自动重开。

需要 Reach 时可直接运行 `agent-reach execute CHANNEL ACTION --params '{...}'`，公开路径成功就返回，剩余站内请求才准备依赖和会话。`ensure CHANNEL` 留给站内安装验收和排障；需要本人登录会返回明确提示。`execute` 返回 `operation_id` 时，在用户完成后运行 `agent-reach resume OPERATION_ID`，直接验证待完成的站内动作。本版没有 ask 或 Reach MCP 服务，无需模型 API Key。

优先按站点复用本地已有登录；默认使用已连接的浏览器，只读复制当前网站 Cookie。多个来源对应不同账号时，用 `browser profiles` / `browser use ID` 选择，不随机切换。来源不可用时保留 Reach 已保存的会话。定期保存会话；真实页面操作和 Reach 调用重置十分钟计时。OpenCLI Bridge 随浏览器启动和回收；已有用户进程保留，版本冲突交由用户处理。详细步骤见 [sessions.md](references/sessions.md)。

`agent-reach add CHANNEL` 会准备渠道所需依赖、专用浏览器和插件；`remove CHANNEL` 清除该网站的登录和存储，保留其他网站。小宇宙保留为可选转录渠道，需要 Groq Key。

安装、升级和清理只处理台账记录的 Reach 文件。普通查询不升级依赖、不启动更新检查、不写其他软件配置。渠道需完成真实查询验收才能发布；doctor 和单元测试不代替验收。
