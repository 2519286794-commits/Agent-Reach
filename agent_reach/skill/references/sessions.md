# 会话与专用浏览器

所有浏览器渠道共用 `~/.agent-reach/browser/profile`。CloakBrowser 优先，安装或下载失败时使用已安装的 Chrome。Node、OpenCLI、内核和扩展由 `agent-reach add CHANNEL` 自动准备；CloakBrowser 的扩展自动加载，Windows Chrome 回退路径可能需要点击一次“添加至 Chrome”。

专用浏览器由 watcher 管理，闲置 10 分钟自动关闭；查询自动准备和重开。此配置与日常 Chrome 分开，程序不关闭用户的日常浏览器。

## 使用与登录

1. 公开内容先用 Agent 已有搜索和读取，结果足够就回答。
2. 需要站内动作时，`agent-reach execute CHANNEL ACTION --params '{...}'` 执行真实请求。不要为每个请求先跑一次 ensure 的测试查询。
3. 只有实际返回 NEED_LOGIN 才请用户登录；`agent-reach login CHANNEL` 打开专用浏览器，登录由用户本人完成。BOSS 等原生工具按返回提示执行 `login CHANNEL --sync`。
4. 若返回 operation_id，用户完成后使用 `agent-reach resume OPERATION_ID`。保存的是任务参数，不会为等待登录另起常驻任务服务。

## 一次性继承登录

专用浏览器已有登录优先复用。用户明确同意导入指定网站后：

```bash
agent-reach browser profiles
agent-reach browser import xiaohongshu --opencli-profile SOURCE_ID
# 或者只读用户指定的本地登录文件：
agent-reach browser import xiaohongshu --state-file /absolute/path/session.json
agent-reach check xiaohongshu --search --text
```

来源是用户选定的已连接 OpenCLI profile；不读取 Chrome Cookie 数据库，不导出其他网站，不输出 Cookie/Token。导入只复制该站 Cookie，无法保证所有平台都接受新环境，需要实际查询确认。没有长期自动导入授权。原浏览器和原文件保持不变。

旧版 Reach 自有会话会从 `sessions/CHANNEL-cloak/profile/reach-session.json` 一次性合并到共用配置，只补缺失 Cookie，保留已有的新登录。来源属于 Reach 自己；个人 Chrome 仍需明确授权导入。

CloakBrowser 下载失败后会记住 Chrome 回退，避免每次查询重新下载。修好网络后可用 `agent-reach browser setup --retry-cloak` 重试。

## 退出和删除

`agent-reach logout CHANNEL` 清除专用浏览器中该站登录和渠道自有状态。`remove CHANNEL` 还清理该渠道授权与待完成任务，保留其他网站登录。退出不修改来源 Chrome。限流或验证码时停止，不换账号或浏览器反复尝试。
