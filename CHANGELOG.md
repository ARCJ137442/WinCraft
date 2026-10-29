# 变更记录

## Unreleased — 配置包运行时接入（2026-10-30）

- 本机世界管理器支持预览并应用声明式 `.wcp`：有界归档检查、来源/权限匹配、显式 grant 后 generation 失效与重新预览、确认后只创建新世界、Provider 定向加入事件以及基于内存 ledger 的两步回退；不替换已有世界，不下载或运行 adapter。
- Provider import 仅在 `0.4-preview.1` capability 表中声明，Provider SDK 缺少能力/claim 时失败关闭；稳定协议 0.3 不增加导入方法。
- B06-01/02 在各自验收范围 VERIFIED；B06-03/04 的自动化/静态部分已实现，但管理器原生 UI 和两个用户环境的分享验收仍 PARTIAL/NOT_RUN。当前本地候选构建不是已发布发行版。

## Unreleased — provider inventory 与 Agent 会话卡片（2026-10-29）

- 增加 opt-in `0.4-preview.1` endpoint-local `provider.inventory.register/list`；来源自报 capability 不产生 grants，跨 Host 发现由调用者显式选择并鉴权。
- Global Agent Overview 的默认总览与来源列表统一展示 Codex CLI、Claude Code、Codex App 的会话名称、状态、项目与有界 Agent 输出；Codex Desktop 本机状态 DB 按 `originator` 提供标题/项目回退，并只从 session ID 匹配的 rollout 尾部读取 Agent 消息；bridge 按 thread ID 补充实时字段，缺失状态显示未知。Codex CLI 只读最近四个线程的 `agentMessage`，Claude 只读活动会话日志尾部并忽略用户/工具/思考块。
- Live Agent Overview 新增显式 `--sources` 选择；未选择来源不启动对应适配器、不复用其旧数据，并显示“本轮未查询”。可在 Codex App 目标停滞期间只监控 Codex CLI 与 Claude Code。
- Popup-Ask 临时问答窗请求 `surface_opacity=0.92` 以提高阻塞提问的可读性；其他浮窗仍保持全局 0.8 默认。
- 当前 Windows release 的合成 UIA smoke 已看到四字段；真实 Codex App connector 快照和 UUID 深链接仍为 `BLOCKED/NOT_RUN`，不宣称真实会话已经接入。

## Unreleased — 原生窗口动作与 Obsidian Workspace 交互（2026-10-27）

- 增加 Tauri-only、能力门控的 `native_window_action`：仅 `obsidian`、`traffic_monitor` 白名单应用和 `activate`、`restore`、`minimize` 枚举动作；用户触发后由宿主在同一 revision/lease 验证下执行，不开放 shell、AHK 或任意进程路径。
- Obsidian Workspace 标题可激活已有 Obsidian 窗口，可选按标题子串筛选；接入 Obsidian 暗紫主题、SVG 图标、状态颜色和仅统计可见前五项的分布图，关闭健康连接噪音与默认文本选择。
- 对齐 `appearance`、`icon`、`bar_chart`、嵌套 JSON Pointer 绑定的 JSON Schema 与 Rust 校验；补充 Agent 提供者 Skill 原生窗口动作教程和 synthetic 协议样例。
- Popup-Ask provider 增加跨进程单槽互斥；第二个同时调用在连 Host/创建世界前返回 busy，并引导用户到世界管理器找到现有请求，避免重复 Popup 与抢焦点。

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
- 可提交的实测摘要与未完成的人工验收见 `docs/engineering/VALIDATION.md`；脱敏命令日志与机器专属证据保存在默认忽略的 `evidence/local/nextgen-2026-10-26/`。

## 0.1.0-alpha.1 — 2026-10-25

原型交接：Rust世界/租约内核、Axum协议服务、Tauri托盘与窗口适配、内部管理提供者、10类声明式组件、动态场景patch、Python提供者与只读外心桥接、源追踪和验收文档。

验证完成范围为TS/Node/离线契约/浏览器DOM；Rust、真实协议与Windows尚未验收。没有发布、推送或注册正式产品名。
