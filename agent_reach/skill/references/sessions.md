# 会话与专用浏览器

所有浏览器渠道共用 `~/.agent-reach/browser/profile`。CloakBrowser 优先，安装或下载失败时使用已安装的 Chrome。Node、OpenCLI、内核和扩展由 `agent-reach add CHANNEL` 自动准备；CloakBrowser 的扩展自动加载，Windows Chrome 回退路径可能需要点击一次“添加至 Chrome”。

专用浏览器由 watcher 管理，闲置 10 分钟自动关闭；查询自动准备和重开。此配置与日常 Chrome 分开，程序不关闭用户的日常浏览器。

## 使用与登录

1. 公开内容先用 Agent 已有搜索和读取，结果足够就回答。
2. `agent-reach execute CHANNEL ACTION --params '{...}'` 对已声明的公开路径先搜索/读取，成功就返回；不足时才准备站内依赖与会话。`--backend public-web` 限定公开查询；指定 `--backend opencli` 等声明后端可直接使用站内能力。不要为每个请求先跑一次 ensure 的测试查询。
3. 只有实际返回 NEED_LOGIN 才请用户登录；`agent-reach login CHANNEL` 打开专用浏览器，登录由用户本人完成。BOSS 等原生工具按返回提示执行 `login CHANNEL --sync`。
4. 若返回 operation_id，用户完成后使用 `agent-reach resume OPERATION_ID`。保存的是任务参数，不会为等待登录另起常驻任务服务。

## 默认无头，优先复用已有登录

查询默认 headless，不弹窗口。`login CHANNEL` 专门给本人登录，会显示窗口；下一次查询先保存，再用同一配置转回无头。先恢复保存的会话，再打开目标页。

第一次调用网站时，优先从已连接的本地浏览器只读复制该站 Cookie；不会复制整个 Chrome 目录、其他网站登录、访问密码库或修改来源。没有可用来源时继续用 Reach 保存的会话，包括旧版分站快照。Cookie 存在不代表登录有效，必须看真实动作结果。

原 Chrome 需已连接官方 OpenCLI 扩展；未连接时不能承诺自动复用，也不据此认定账号未登录。只有实际需要本人登录时才打开专用窗口。Cloak 内核不依赖该来源才能启动；已有专用会话仍可独立复用。

多个本地浏览器都可能有该站账号时：`browser profiles` 查看连接，`browser use ID` 选择来源。`login CHANNEL --import-existing` 可主动刷新该站登录，不打开登录窗口。首次复制成功后持续复用保存的会话，不按时间重新导入；退出和删除渠道后停止自动导入，避免登录复活。

复用以该站 Cookie 快照为准，清除专用浏览器中来源没有的旧 Cookie，保留其他网站。导入失败会尝试恢复原站点 Cookie，并保留已保存的会话。切换来源不会撤销已退出的渠道，也不覆盖本人明确选择的专用登录。

BOSS 站内搜索优先走 OpenCLI，共用该配置。JD 的 OpenCLI 提取在部分职位上存在上游误报登录问题，不据此要求用户反复登录。原生 Boss CLI 仍可显式选择；其 JD 读取需要同一原生 CLI 搜索产生的短期引用，引用只保存在本地，不返回给模型。公开网页结果另行标注。B站只在读字幕时尝试把已有站点登录交给官方 B站 CLI，普通搜索不准备浏览器；没装 OpenCLI 时，仍可沿用保存的 B站 CLI 登录。雪球社区动作会自动同步已有登录，无需额外执行同步命令。

登录期间定期保存，无需关窗才能保存。真实页面操作和 Reach 调用重置十分钟计时。OpenCLI Bridge 随专用浏览器由计时程序管理；Reach 启动的桥随浏览器退出，用户已有桥保留。

CloakBrowser 下载失败后会记住 Chrome 回退，避免每次查询重新下载。修好网络后可用 `agent-reach browser setup --retry-cloak` 重试。

## 退出和删除

`agent-reach logout CHANNEL` 清除专用浏览器中该站登录和渠道自有状态。`remove CHANNEL` 还清理该渠道授权与待完成任务，保留其他网站登录。清理失败保留渠道记录，用户可重试清理。限流或验证码时停止，不换账号或浏览器反复尝试。
