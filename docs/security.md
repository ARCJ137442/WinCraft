# 安全边界与威胁清单

## 本原型不是安全认证过的通用远程执行平台

设计上减少权限面：外部只发声明，不执行上传代码，不开放 shell/fs/任意 URL；原生能力按白名单接线；托盘操作员可撤销租约。2026-10-26 本机已运行真实 Rust/Tauri release、认证/Origin/租约/断线/慢消费者探针和 TrafficMonitor 本机只读桥接，但这不等于渗透测试、ACL 审计或“安全沙箱”认证。

## 已写入控制

随机宿主 token、预升级鉴权、拒绝浏览器 Origin、5 秒 hello 时限、协议版本、每会话 120 消息/秒、单消息 256 KiB、最大 64 会话/16 世界/256 节点/深度 16、有限动作队列与超时、随机世界加入凭证、会话绑定写租约、epoch 撤销、系统世界保护、旧界面动作版本检查。

宿主 token 的比较避免直接逐字节遇错提前返回，但这不是形式化侧信道审计。连接描述文件在 Unix 以 0600 创建；Windows 依赖 app-local-data 的用户 ACL，不能把文件位置本身当作权限保证。2026-10-26 对此前 locale-enabled Tauri build 的单份 descriptor 做过只读 ACL 检查：owner 为当前用户，未发现 Everyone/Authenticated Users/Users/Guests broad-read 授权；当前 lifecycle release 的 descriptor ACL 未检查，旧 build 结果不能外推。以上都不是完整安全审计或跨账户测试。

## 两层认证

host token 允许接入宿主；world join_key 或明确开放策略允许加入某个世界；写租约才允许修改。名称/UUID/发现结果不是授权。内部 operator 角色不是协议字段，外部不能自报。

host token 仍是粗粒度接入凭证，不是成熟多租户身份体系。持有它的程序可申请资源，配额只能限制而不能消除拒绝服务；本原型适合受信任用户与受控机器，不能当公共服务。

## 数据与执行隔离

客户端不知道宿主函数名就能任意执行的模式不存在。组件 action 是不透明业务标识，仅回传对应提供者。提供者业务执行的安全由提供者处理，宿主 action.result 不能证明业务 exactly-once。

跨应用原生操作走单独的 `native_window_action` 白名单。Obsidian 与 TrafficMonitor 只允许对宿主登记的既有窗口执行枚举窗口操作；Codex App 另有 `codex_thread_navigation` capability，只接受 UUID `thread_id` 并由宿主构造固定 `codex://threads/<UUID>` URI。不会接受任意 URL、shell 命令、可执行路径、AHK 源码或任意代码。Rust/Tauri 宿主校验场景 revision、活动 writer lease、组件 disabled 状态及 capability，并且仅在用户点击时调用 Windows URI 处理器；headless 与非 Windows host 拒绝该 Codex 动作。Windows 接受 URI 只证明跳转请求已交给系统，不证明 Codex App 已加载会话。关闭窗口、手动启动进程、原始坐标/句柄和自动动作不属于此 allowlist。

窗口状态订阅按 WebSocket session 绑定，只能订阅已加入世界的有限类型，并只发出最小状态。读者订阅不授予写权；leave/destroy/disconnect 清理订阅。窗口状态事件不会自动触发本地动作；订阅与动作授权分离。

Renderer 使用 textContent/DOM 原语，禁用 HTML 和脚本注入。JSON Pointer 不穿越 prototype/constructor。CSP 禁止外部框架、iframe 和任意脚本；样式只使用宿主选定属性及有限数值。

各 WebView 使用相同应用资源来源，属于可信宿主代码，不构成可运行恶意第三方脚本的隔离容器。将来若允许自定义可执行组件，必须重新设计来源、能力、存储和进程隔离。

## 远程

仅绑定 loopback；不提供“无 TLS 但听在 0.0.0.0”的便捷开关。远程通过 SSH 等由用户配置的受保护隧道接入。纯公网、多用户长期授权、证书/撤销/审计是后续阶段。

## 需要本地重点检验

错误 token、带恶意 Origin、过大/过深 JSON、慢消费者、并发写租约、旧租约重放、重复 action ack、过期事件、事件节点变更、接管后重连争抢、renderer 是否能越权访问其他世界、Windows descriptor ACL 的跨账户/继承边界、多实例端口冲突、退出时令牌文件清理。

不记录业务 payload 和 token。native.log 仅记录世界 ID、窗口意图版本和原生错误。公开证据仍需检查路径和标题是否含个人信息。

## 公开仓库前的资料审查

WinCraft 核心、Provider 和应用按独立仓库维护；子项目使用 `wincraft-XXX` 命名。世界归档只能保存不含真实业务状态的声明式蓝图、schema 和合成 fixture。真实 Obsidian 笔记、Agent 会话、通知正文、外心档案、TrafficMonitor 遥测及运行中的世界状态不进入 Git、release 包或公开截图。

公开前扫描暂存/未跟踪/跟踪文件和全部可达 Git 历史、tags、LFS、release 附件及截图。审查 bearer token、API key、私钥、`.runtime.json`、环境文件、机器绝对路径、账户/档案/会话标识、日志和第三方来源。`.gitignore` 只降低误提交风险，不证明内容已脱敏；`evidence/local/` 也不能直接分享。就地扫描工作树，避免把含凭据文件复制到临时目录；扫描器输出必须隐藏匹配值，只保留脱敏定位。发现历史凭据时先撤销/轮换，再清理完整历史；历史个人信息须在重新公开前移除或改用经审查的干净公开历史。

本次预检使用 Gitleaks 检查了可达历史与工作目录：历史未发现凭据规则命中；本地忽略的旧证据目录中仍有测试 `.runtime.json` 命中凭据规则，未纳入 Git 跟踪。另发现一条旧提交的本机路径曾进入公开历史。当前仓库因此不能宣称已完成公开准备；详细发布门槛见 [`governance-release-checklist.md`](governance-release-checklist.md) 与 [`engineering/VALIDATION.md`](engineering/VALIDATION.md)。
