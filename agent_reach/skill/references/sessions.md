# 会话与专用浏览器

所有浏览器渠道共用 `~/.agent-reach/browser/profile`。CloakBrowser 优先，安装或下载失败时使用已安装的 Chrome。Node、OpenCLI、内核和扩展由 `agent-reach add CHANNEL` 自动准备；CloakBrowser 的扩展自动加载，Windows Chrome 回退路径可能需要点击一次“添加至 Chrome”。

专用浏览器由 watcher 管理，闲置 10 分钟自动关闭；查询自动准备和重开。此配置与日常 Chrome 分开，程序不关闭用户的日常浏览器。

## 使用与登录

1. 公开内容先用 Agent 已有搜索和读取，结果足够就回答。
2. 需要站内动作时，`agent-reach execute CHANNEL ACTION --params '{...}'` 执行真实请求。不要为每个请求先跑一次 ensure 的测试查询。
3. 只有实际返回 NEED_LOGIN 才请用户登录；`agent-reach login CHANNEL` 打开专用浏览器，登录由用户本人完成。BOSS 等原生工具按返回提示执行 `login CHANNEL --sync`。
4. 若返回 operation_id，用户完成后使用 `agent-reach resume OPERATION_ID`。保存的是任务参数，不会为等待登录另起常驻任务服务。

## 保存与复用

只复用 Reach 专用浏览器中已保存的登录。程序不读取个人 Chrome 的 Cookie、登录文件或账号，也不提供导入入口。首次需要登录时，由用户在专用窗口完成。

登录期间会定期保存会话，无需关窗才能保存。鼠标点击、键盘和滚动等真实页面操作以及 Reach 调用会重置十分钟计时；没有操作时自动关闭，下次查询自动重开。网站要求扫码、验证码或确认时交给用户，失败不反复开窗。

OpenCLI Bridge 随专用浏览器由计时程序启动、回收。已有的兼容 Bridge 可复用，Reach 不关闭用户启动的进程；若另一个浏览器正在使用 Reach 启动的桥，保留并在状态中说明。版本冲突时提示用户处理，不自动重启别人的服务。

CloakBrowser 下载失败后会记住 Chrome 回退，避免每次查询重新下载。修好网络后可用 `agent-reach browser setup --retry-cloak` 重试。

## 退出和删除

`agent-reach logout CHANNEL` 清除专用浏览器中该站登录和渠道自有状态。`remove CHANNEL` 还清理该渠道授权与待完成任务，保留其他网站登录。清理失败保留渠道记录，用户可重试清理。限流或验证码时停止，不换账号或浏览器反复尝试。
