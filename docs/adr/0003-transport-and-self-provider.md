# ADR-0003：共享 Rust 宿主，WS 起步，管理器走内部提供者

状态：本轮实施取舍；真实 Rust WebSocket、release Tauri 与内部管理器/外部 provider 已部分验证，远程 SSH/TLS 部署仍未测试。

选择：一个 Rust 宿主管理所有世界。HTTP 发现 + WebSocket 双向通道；默认 loopback 与运行时令牌。内部管理器通过 Hub.dispatch/相同 Scene/事件模型自用，不绕本机网络。Tauri 本地能力是宿主执行器，不开放任意调用。

理由：减少每窗/每提供者重复应用进程，便于统一调度；保留提供者跨机器身份；优先证明语义而非同时维护多传输。共享 renderer 可以证明通用组件是否足够表达自己的管理 UI。

代价：Mutex 与全快照广播存在扩展上限；OS/WebView2 仍可能多进程；内部 operator 有特殊权限，不能包装成与外部提供者完全相同的权限边界。

后续：用性能证据决定通道升级；用安全评审决定 LAN/TLS/浏览器支持。
