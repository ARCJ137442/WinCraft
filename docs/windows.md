# 原生窗口能力矩阵

**“接线”描述实现覆盖范围，不单独代表运行通过。** 可提交的本机验证摘要见
[`engineering/VALIDATION.md`](engineering/VALIDATION.md)；机器专属细项位于默认不提交的 `evidence/local/nextgen-2026-10-26/`。

| 能力 | 当前状态 | 语义/限制 |
|---|---|---|
| 多世界与托盘宿主 | 接线 | 一个宿主管理多个 WebViewWindow；并非每世界独立应用 |
| 标题/逻辑尺寸 | 接线 | 宽 160–2400，高 80–1800；原型限额可后续调整 |
| 桌面物理位置 | 接线 | 可负坐标；离屏/Windows 隐藏哨兵值回工作区右下角 |
| 置顶/显隐/任务栏/装饰 | 接线 | `visible` 默认显示；最小化仅隐藏、不销毁 world/lease，provider 可配置，管理器可恢复 |
| 自定义标题栏 | 接线 | 默认显示、固定在滚动工作区外；provider 可通过 `title_bar_visible` 隐藏/显示；X 仍执行关闭语义 |
| 标题栏折叠内容 | 接线（当前待实机复验） | 标题栏单击且移动小于 5px 时折叠/展开下方内容；超过阈值才启动原生拖动；世界、租约和组件树不变 |
| 托盘全局临时隐藏/显示 | 接线（当前待实机复验） | 隐藏全部逻辑可见的 native windows，保存恢复集合；不改 provider `window.visible`、世界或 lease。托盘显示全部时，仅恢复仍逻辑可见的窗口 |
| 在线状态行 | 接线 | 正常 `online` 时隐藏状态行；stale/vacant/启动等状态继续显示，错误仍通过 alert 呈现 |
| 人类拖动 | 接线 | 经自定义 surface_drag 验证 human 模式 |
| 提供者控制几何 | 接线 | 显式 provider 模式；用户默认可调整宽度的 human 模式下，provider 不得覆盖位置/尺寸 |
| 工作区语义锚点 | 已实现（核心/Schema/Tauri 自动检查） | provider geometry 下可配置当前 monitor work area 的四角与逻辑边距；host 按 monitor DPI 换算并夹取到工作区。human 几何模式拒绝配置，本地 rescue 清除锚点。显示器拔除后的自动迁移尚未原生实测 |
| 点击穿透 | 接线 | 默认关闭；provider 可配置；全窗穿透时按钮不可点击，依赖管理器/托盘接管恢复 |
| 悬浮面透明度 | 已有 CSS 渲染 | 默认 surface_opacity=0.8，provider 可用 window.configure 调整；OS 原生窗口背景保持透明 |
| 默认文本选择 | 已接线 | 默认 `text_selectable=true`，provider 可读写；内容组件可用自身样式覆盖，标题栏保持不可选 |
| 管理器超高内容 | 接线 | 标题栏、状态栏和页脚固定；manager scene 独立滚动，工具栏 sticky；窗口级滚动条隐藏 |
| 原生执行结果 | 接线 | pending/applied/error；可能部分原生调用先成功再失败，报告而非假装回滚 |
| 跨应用窗口动作 | 接线（人工点击验收待做） | `external_window_actions` 仅在原生 Windows host 宣告；宿主登记 Obsidian/TrafficMonitor app ID，支持 activate/maximize/restore/minimize 与有界 title substring；单一匹配直接执行，多匹配仅使用当前前台匹配窗口，否则明确要求收窄筛选；headless 拒绝，不启动程序、不执行任意命令 |
| 窗口状态事件订阅 | PASS（真实 headless WebSocket） | 连接级订阅已加入世界的几何/逻辑显隐状态；读者不获写权，leave/destroy/disconnect 自动清理；watch 最新值与 occurrence 广播分流，慢消费者 resync/disconnect。Tauri release 已构建、未启动。|
| 人类移动回写投影 | 接线 | 不保存磁盘；已观测几何不回声式重设造成拖动抖动 |
| 多屏位置恢复 | 部分接线 | 创建/应用配置/托盘找回检查工作区；自动拔屏全周期仍需扩展 |
| Windows 虚拟桌面“所有桌面” | 未实现（平台 API 阻塞） | 用户要求默认关闭、provider 可选打开；当前 Tauri/tao `visible_on_all_workspaces` 明确标记 Windows 不支持，公开 `IVirtualDesktopManager` 只提供单个 desktop 的查询/移动。不会把 no-op 当成成功；要实现需决定是否接受私有 Shell COM API 的维护风险 |
| 光标跟随 | 未实现 | 后续宿主本地行为引擎；不在提供者每帧传坐标中硬凑 |
| 附着其他应用窗口 | 未实现 | 需 Win32 目标身份/生命周期/权限处理 |
| 调整焦点/快捷键/任意窗口探查 | 未实现 | 不把‘全部 Windows 能力’写成已覆盖事实 |
| 跨平台桌面 | 未验收 | 核心跨平台设计不等于原生行为同等可用 |

## 2026-10-26 本机实测摘要

- `npm run desktop:build` 成功；E: 临时 target 下的独立 release EXE 使用 `--open-manager` 启动，真实 TrafficMonitor 与 Obsidian Workspace provider 均接入该实例。不带该参数仍保持托盘优先。
- 当前 release 接入 TrafficMonitor V1.86 x64 Lite，实际 `OnMonitorInfo` 样本持续进入世界；从当前源码重编的桥接快照报告 1.8.6.0，generation/revision 前进，不记录读数。
- 当前 lifecycle release 的 `lease_probe.py` 完成 28 项真实 Tauri-hosted Rust WebSocket 检查，包含严格 0.3 握手、拒绝旧版本、world.list 隔离、`text_selectable` 默认/读写、窗口属性、租约过期/断线 fencing、慢消费者和正向 `scene.patch`；不替代像素和人工鼠标验收。
- 当前 release 的 Obsidian Obsidian Workspace provider 从明确打开的 dashboard 读取只读摘要，native report 为 applied；未写入笔记或插件设置。
- 用户报告最新手工检查中的内容高度/窗口滚动条、动态组件动作等项目通过；但托盘“显示世界管理器”点击无响应，此项需修复并复测。此前版本托盘图标/菜单可用、悬浮窗可见且可拖动。最新 release 的像素级标题栏拖动/折叠、托盘全局隐藏/恢复、无标题栏 HUD、文本选择鼠标手势、多 DPI/显示器、click-through 救援和虚拟桌面行为仍需逐项验收。

## 2026-10-27 原生动作实现状态

Tauri 侧已添加 host-owned 的受限跨应用窗口动作。`surface_interact` 在同一核心锁内验证 accepted scene、revision、有效 writer lease 和 disabled 状态，随后按 allowlist 定位窗口并执行枚举操作，再把原静态动作派发给 provider。当前实际 Obsidian Workspace provider 声明 Obsidian `activate`；单一匹配直接执行，多匹配仅使用当前前台匹配窗口，否则要求更窄的标题筛选，不按枚举顺序盲选。原生动作支持 activate/maximize/restore/minimize；本轮 Rust/schema 检查和独立 release 构建通过，真实用户点击与 Windows 前台限制的成功路径仍待人工验收。

原生资源状态与业务状态分离。收到一个版本化窗口意图后，监督循环尝试应用；失败保留错误，隔一定时间重试。窗口被操作员销毁后移除核心世界并关闭 native 资源。

public renderer 的权限只允许事件订阅及受 Rust 端标签约束的四个自定义 IPC。未开放通用窗口修改权限给前端；修改走核心，不能绕过所有权检查。
