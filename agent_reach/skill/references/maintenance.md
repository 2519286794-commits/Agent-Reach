# 维护

- 已安装时使用 `agent-reach update`，更新后查看实际结果与安装能力表。
- `agent-reach doctor --text` 读取本地状态；`check CHANNEL --search --text` 做一次联网验收。
- `agent-reach browser status` 查看共用浏览器；`browser setup` 准备内核和扩展；`browser stop` 关闭程序管理的浏览器。
- CloakBrowser 下载失败会保留缓存并尝试本机 Chrome。区分依赖下载、浏览器连接、登录、网页加载和平台限流；不要把网络超时说成登录失效。
- 不修改 OpenCLI 安装文件。遇到上游缺陷记录错误和版本，再升级上游或反馈。
- PLATFORM_BLOCKED、RATE_LIMITED、NEED_LOGIN、BUSY 停止本次尝试。需要用户处理后再继续；不反复开窗。
- 卸载先查看 `agent-reach uninstall --dry-run`，确认范围后执行 uninstall；保留用户不属于 Reach 的文件与浏览器。
