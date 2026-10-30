# 已知限制与优先修订项

## P0：必须先核验

2026-10-26 的本机验证已通过 Rust workspace 编译/测试/Clippy、真实 WebSocket 探针、Tauri release 启动和 TrafficMonitor x64 Lite → Python provider → Tauri 窗口的数据链路。它们仍不构成安全认证或对外发布批准。

尚待本机人工/专门环境核验：当前 lifecycle release descriptor ACL、跨账户/继承边界、click-through 救援、不同 DPI/显示器、休眠恢复、发布签名/安装器和原生 revision-conflict/IME 目视路径。此前 locale-enabled build 的单文件 owner/broad-read ACL 检查不能外推到当前 descriptor；浏览器预览不能替代其他验收。可提交摘要见 `docs/engineering/VALIDATION.md`；机器专属细项位于默认忽略的 `evidence/local/nextgen-2026-10-26/`。

## P1：已知设计局限

- 首版最大 16 世界，包含内部管理器；不是无限多个世界。
- 稳定协议 0.3 仍是整窗独占写租约；不相交 scope writer 只在显式 opt-in 的 `0.4-preview.1` 实验路径可用，尚无稳定协议承诺，也不支持同一 scope 多人编辑。
- API 仍使用全快照，没有通用 scene/data 增量协议或无损事件日志；另有连接级几何/逻辑显隐状态订阅，允许合并中间状态。
- 普通请求 ID 不是幂等键；响应超时不能自动重发有副作用动作。
- 原生设置可能部分成功；提供错误报告但不保证 Windows API 多属性事务回滚。
- provider 几何模式不能抵御其他高权限应用或操作系统所有移动途径。
- 主机休眠、系统时钟/单调时钟表现必须本机验证；未给严格跨休眠 lease 保证。
- 输入草稿无磁盘恢复；世界/借用关系/设置重启即丢失。
- 没有应用单实例插件。若同时启动多个宿主，它们拥有不同 host_id/随机端口/独立描述文件；不是自动合并成一个宿主。
- 管理器刷新与原生窗口监督为朴素定时模型；无高性能结论。
- 桌面窗口 bootstrap 若事件订阅失败会显示错误，尚无完整 UI 重连重试界面。
- 原生 resize/move 观测与布局边界仍可能存在平台特定竞争，需拖动/DPI 实测。
- Windows descriptor ACL 曾在此前 locale-enabled build 上只读检查；当前 lifecycle descriptor 与跨账户继承/其他安装路径尚未核验。
- Windows 虚拟桌面“所有桌面”已列入用户要求，但当前 Tauri/tao 公共 `visible_on_all_workspaces` API 在 Windows unsupported。未启用私有 Shell COM 接口；该属性保持未实现并等待方案选择。

## P2：明确不在首版

稳定组件级多写者协议与长期角色授权、任意前端插件、可视化搭建器、第三方网页加载、浏览器直接 Origin 接入、内置 TLS、公网服务、自动发现局域网主机、附着外部窗口、光标跟随、完整窗口探针、桌宠状态机、移动端。

## 不能用来‘修复’的捷径

删除鉴权让 demo 连得上；让多个提供者直接覆盖 root；重新启用任意 JS；将所有窗口做成 Electron；用 JS mock 替掉 Rust 引擎；用默认外心端口/anonymous 掩盖 readiness 问题；捕获并吞掉 native 错误；关闭所有测试来宣布编译成功。
