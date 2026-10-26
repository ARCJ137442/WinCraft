# 变更记录

## Unreleased — 本机联调（2026-10-26）

- TrafficMonitor 桥接切换为消费官方 V1.86 `OnMonitorInfo` 回调；增加本地状态侧文件诊断，不写遥测值。
- Tauri release 支持显式 `--open-manager` 启动参数，默认仍为托盘优先。
- `lease_probe.py` 增加真实服务的 insert/move/replace/props/remove 正向 patch 验收；TrafficMonitor provider 可输出不含指标值的同步状态行。
- 人工几何窗口默认可调整宽度；横向 resize 不再关闭内容高度适配，长文本在窄宽度下限制在组件内换行。
- 新增独立最小化按钮：隐藏保留世界和租约，管理器可重新显示；provider 通过 `window.visible` 观察并恢复窗口。
- WebView 原生右键菜单默认拦截；仅静态注册 `context_action` 的按钮/输入会向当前 provider 发送右键动作。
- `surface_opacity` 默认 0.8 且 provider 可读写；管理器世界工作区在内容超过显示器工作区时内部滚动，保持外壳/工具栏，不显示窗口级滚动条。
- 协议升到 0.2：标题栏默认固定显示、click-through 默认关闭，两者都可由 provider 通过 `window.configure` 配置；旧 protocol 版本仍严格拒绝。
- 协议升到 0.3：新增 `text_selectable` 窗口默认属性，默认 true、provider 可读写；renderer 组件样式可覆盖，标题栏文字始终不可选。
- Obsidian Workspace provider 改为从当前实际渲染的 dashboard leaf 读取，跳过空的旧 leaf；仍只读，不写笔记或插件设置。
- 本机实测细节与未完成的人工验收见 `evidence/local/validation-matrix.md`。

## 0.1.0-alpha.1 — 2026-10-25

原型交接：Rust世界/租约内核、Axum协议服务、Tauri托盘与窗口适配、内部管理提供者、10类声明式组件、动态场景patch、Python提供者与只读外心桥接、源追踪和验收文档。

验证完成范围为TS/Node/离线契约/浏览器DOM；Rust、真实协议与Windows尚未验收。没有发布、推送或注册正式产品名。
