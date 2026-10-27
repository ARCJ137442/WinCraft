# Windows 窗口运行时能力路线图

日期：2026-10-26。状态：探索性路线图，供产品与协议后续设计使用；下文能力除明确标注“当前基线”外均未实现，也不构成 Windows 验收结论。

## 目标与边界

WinCraft 不需要把整个 Win32 API 暴露给提供者。Windows 负责执行原生窗口行为；WinCraft 协议表达经过校验的意图、可观察事件和受限动作。提供者不接收任意 `HWND`、窗口过程回调地址、Win32 消息编号、样式位或系统注入代码。

产品不变量继续适用：世界就是窗口；业务真相归提供者；连接和订阅可重建；默认单写者与多快照读者；人类可本地接管；原生操作返回明确结果；高权限能力须由宿主授权并可撤销。原生窗口当前接线和验收状态见 [windows.md](windows.md)，协议当前行为见 [protocol.md](protocol.md)。

## 当前基线：有状态推送和受限状态订阅，尚无注册式事件反应

协议 0.3 已有 `window.configure`、`visible` 等窗口状态、版本化快照和 WebSocket `world.snapshot` 推送。宿主也观察人类移动/缩放并更新快照。因此，提供者不是只能轮询。

2026-10-27 已在协议 0.3 增加连接级 `event.subscribe` / `event.unsubscribe`，按 `window.geometry_changed`、`window.visibility_changed` 筛选已加入世界的状态变化。它建立在当前 snapshot sequence/window_revision 上，可随断线清理；状态事件允许合并，慢消费者仍会 resync/disconnect。它不提供焦点、原生最小化等事件，也没有“事件发生后请求某种宿主动作”的规则引擎，因此仍不支持“窗口最小化时自动把另一个应用带回前台”。

2026-10-27 新增的 `native_window_action` 是一个有限的用户交互入口：按钮收到本地点击后，原生宿主按 allowlist 操作已存在的 Obsidian 或 TrafficMonitor 窗口，支持 activate/maximize/restore/minimize。它是可扩展的宿主窗口服务，不为单个世界写专属 Win32 分支；新应用必须由宿主登记，新操作必须是类型化且有限的。本轮新增最大化，并收紧多窗口选择：单一匹配直接执行，多匹配仅使用当前前台匹配窗口，否则失败并要求更窄的标题筛选；不再按枚举顺序盲选。真实原生点击路径仍需用户验收。目前不订阅最小化/焦点事件，也不自动触发动作；后续事件响应需要独立的订阅权限与撤销语义。

### 通用宿主能力的分层

这两类 API 要保持清楚的职责边界：

- `window.configure` 修改当前 world 所拥有窗口的属性，例如尺寸、透明度、显隐、标题栏和穿透。
- `native_window_action` 让用户点击 world 中的声明式控件后，请宿主操作另一款已登记应用的现存窗口。它不把另一个应用纳入当前 world，也不把业务状态转给 WinCraft。
- 托盘菜单的“暂时隐藏/显示全部”属于本地宿主的全局救援动作，不要求任何 provider 租约，也不改各 world 的逻辑可见状态。

沿这个模型，值得逐步加入的通用能力按依赖和风险排序：

1. **原生状态事件**：订阅显示/隐藏、最小化/恢复、焦点、几何与显示器/DPI 变化。先做会话级订阅、取消、合并与慢消费者处理，再讨论自动响应；不能订阅一次就获得动作权。
2. **语义位置和尺寸**：以当前显示器工作区角落、边缘偏移和受限锚点为主，宿主处理 DPI 与屏幕边界；不让 provider 每帧发送原始坐标。协议 0.3 当前加入 `anchor` 首项，只在 provider geometry control 下可用；角落相对解析时所选 monitor 的 work area，逻辑边距乘该 monitor scale factor，窗口被夹在 work area 内。人类控制时拒绝锚点，本地 rescue 清除锚点。Tauri 只公开 ScaleFactorChanged，不提供显示器拔插事件；拔屏迁移仍属 NOT_RUN。
3. **Shell 曝光与桌面范围**：分别建模置顶、任务栏、Alt+Tab、虚拟桌面可见性；不压成一个 `always_on_top` 开关，也不把平台 no-op 当成功。
4. **用户建立的窗口组**：托盘或管理器可批量显隐/排列独立 world；每个 world 仍保有自己的提供者、lease、撤销和本地接管。
5. **外部应用适配**：若将来要移动、置顶或附着其他应用窗口，先设计用户批准的应用登记与窗口身份生命周期，不能把任意 HWND、进程路径、关闭/启动指令暴露给 provider。

前两项可沿当前协议和 Rust 宿主渐进扩展；Shell、虚拟桌面和附着需要单独的 Windows 原生 POC 与版本矩阵。破坏性关闭、启动进程、任意脚本/消息和无人确认的焦点抢占不作为普通 provider 能力。

后续应把类型事件建立在现有 `sequence` 与 `window_revision` 顺序上，而不是另建第二份窗口真相。可供讨论的事件类别包括：

- 用户或宿主引起的位置、尺寸、工作区、DPI 与显示器变化；
- 显示、隐藏、原生最小化、恢复、关闭请求；
- 激活与焦点变化；
- 主题或系统显示偏好变化；
- 经用户同意的指针区域进入/离开、热键和拖放事件。

### 事件与反应的候选契约

注册应是会话级、可取消的，并注明世界、事件种类、来源和权限；断线后自动失效，不暗中形成永久的窗口—提供者绑定。事件沿用单调 `sequence`，携带 `window_revision`、事件 ID、来源（人类/宿主/系统/提供者）与必要的最小数据。高频移动由宿主本地合并、限速；不把每个鼠标帧通过网络转发。

以下仅为讨论用伪结构，不是当前 API：

```json
{
  "subscribe": ["visibility.changed", "geometry.changed"],
  "scope": "current-world",
  "delivery": "coalesced"
}
```

响应仍是另一项明确、类型化的请求，走宿主授权、版本检查与原生回执。不能因订阅一个事件就授予聚焦其他应用、注册全局热键或读取麦克风的权力。事件触发频率、循环因果、过期订阅和慢消费者需要明确的界限。

**候选用户故事（未实现）：**林遥专注写笔记时把悬浮计时器最小化。Obsidian 提供者订阅到“窗口已隐藏”事件，向 WinCraft 请求激活用户允许的 Obsidian 窗口。宿主只解析白名单应用身份，不把任意 HWND 交给提供者。Windows 若拒绝前台切换，宿主回报受阻；不能伪造成功或绕过焦点限制。微软明确允许系统拒绝 `SetForegroundWindow`，所以协议应表达激活请求，不能承诺“强制抢焦点”。[SetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setforegroundwindow)

## 从 Windows 原生能力导出的路线

| 能力域 | 可形成的 WinCraft 能力 | 默认与设计边界 | 路线阶段 |
|---|---|---|---|
| 窗口事件 | 移动/缩放/显示状态/焦点/显示器变化订阅，受限响应 | 默认只发送最小状态；按会话订阅；高频事件在宿主合并 | 1 |
| 语义位置与运动 | 主/当前显示器工作区角落锚定、距边缘偏移、贴边、有限动画、手动/程序几何交接 | 默认人类可控；运动由宿主本地执行并设速度/边界；不让 provider 每帧推坐标 | 2 |
| 焦点与 Shell 曝光 | 请求前台、任务栏可见性、Alt+Tab 可发现性、任务栏状态展示 | 分开表达置顶、焦点、任务栏和 Alt+Tab；系统不支持某组合时报告有效结果 | 2–3 |
| 主题与合成 | 预设视觉主题、经验证的颜色 token、DWM 背景/圆角/窗口层透明效果 | 先提供预设；高级自定义限于主题 token，不接收任意 CSS；逐 Windows 版本验证 | 3–4 |
| 指针与输入 | 可交互、整窗穿透、命名区域交互、经授权的快捷键/拖放 | 初级使用简单开关；高级使用带版本的枚举/联合配置；默认不注册全局热键 | 3–4 |
| 系统托盘/通知/AppBar | 提供者请求宿主通知；可选任务栏摘要；用户选择的屏幕边缘停靠 | 宿主默认只保留一个托盘入口；逐世界托盘图标、通知和 AppBar 默认关闭；AppBar 会占用工作区 | 3–4 |
| 语音输入与朗读 | 用户主动启动一次语音会话；宿主可读出声明式文本，或把识别出的文本交给当前提供者 | 麦克风默认关闭；界面显示录音中并允许立即取消；不做常驻监听，不留存音频；具体 Windows API 和打包权限先做原生 POC | 4 |
| 捕获可见性 | 用户选择是否让单个窗口避开部分系统截图/录制路径 | 默认关闭；说明适用范围和系统支持状态；绝不宣传为保密或 DRM | 4 |
| 窗口组合 | 将多个独立世界临时组成可移动、显隐的窗口组 | 作为未来方向；保留世界 ID 与各自所有权，另行设计组生命周期、原子操作和冲突规则 | 5 |
| 可访问性 | 将组件角色、名称、值与动作映射到 Windows UI Automation | 让屏幕阅读器和自动化读取语义；验证 WebView2 实际 UIA 树，不假设 DOM 会自动满足需要 | 2–4 |

这张表描述产品机会，不意味着每项能力都应该进入首版。Windows 可管理窗口的矩形、可见状态、Z 顺序和最小化/最大化状态；显示器 API 可定位工作区并换算 DPI；窗口样式、DWM、Shell 和 UI Automation 提供不同的扩展面。[窗口功能](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features) [扩展窗口样式](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles) [SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos) [多显示器定位](https://learn.microsoft.com/en-us/windows/win32/gdi/positioning-objects-on-multiple-display-monitors) [DPI 开发](https://learn.microsoft.com/en-us/windows/win32/hidpi/high-dpi-desktop-application-development-on-windows)

### 移动与组合：让窗口“动起来”，不把动画变成网络负担

语义位置应优先于持续坐标流，例如“当前显示器工作区右下角，向内偏移 24 逻辑像素”“跟随用户允许的目标应用所在显示器”。窗口贴边、移动轨迹和缓动应作为宿主本地策略；远端提供者提交目标意图和速度界限，宿主负责 DPI、工作区夹取、动画和原生回执。

“附着其他应用窗口”比锚定显示器更难：目标程序会关闭、改标题、重建窗口或跨越权限边界。实现时需要稳定的用户认可应用身份、重连行为与脱离规则；不能把标题字符串或猜出的 HWND 当作长期身份。

后续组合多个世界可借鉴“一个宿主进程管理多个世界”的架构，但这只是可行起点，不代表组合能力已存在。正式设计前要确定组合是用户临时建立的布局、提供者创建的工作区，还是可保存蓝图；无论哪种，都要保留每个世界的独立租约和本地接管能力。

### 任务栏、Alt+Tab、托盘与桌面边缘是独立的产品旋钮

小悬浮窗默认不占用 Alt+Tab；用户可选择让它显式出现，或交给世界管理器统一召回。任务栏可见性、Alt+Tab 可发现性、置顶和焦点不可合并成一个 `always_on_top` 开关。Windows 的 Tool Window/App Window 样式对任务栏和 Alt+Tab 有不同的组合行为；协议应表达用户目标，适配器报告实际结果，而不是承诺任意组合都能实现。[扩展窗口样式](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles)

TrafficMonitor 可以作为“任务栏状态展示”的体验参考，但在映射到原生 API 前应确认它实际使用的是独立工具窗口、任务栏按钮、边缘停靠还是其他方式。不能仅凭外观把它等同于 AppBar。真正的 AppBar 会向系统占用桌面工作区并和任务栏协商位置，适合用户显式开启的侧栏模式，不适合默认悬浮窗。[AppBar](https://learn.microsoft.com/en-us/windows/desktop/shell/application-desktop-toolbars) 托盘和 Shell 通知也应由宿主管理；多个提供者可以请求通知，但不应默认各自在通知区域创建永久图标。[通知区域](https://learn.microsoft.com/en-us/windows/win32/shell/notification-area)

### 主题：先选预设，再允许受控定制

当前主题保留为默认预设。之后可增加“紧凑”“放大化”“低干扰”“高对比”等命名预设；名称与清单只是候选，不是冻结设计。Agent 先选择一个预设，再可编辑受限的颜色、字号、圆角和间距 token，形成类似 Minecraft 数据包的主题包。

主题包应由宿主校验结构、对比度与允许值，不能直接注入任意 CSS、脚本或系统句柄。DWM 材质与系统圆角属于进阶外观层，要逐 Windows 版本测试；不支持时回退到 WinCraft 自己的主题，并说明回退状态。[DWM 窗口属性](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmsetwindowattribute) [窗口圆角](https://learn.microsoft.com/en-us/windows/apps/desktop/modernize/ui/apply-rounded-corners)

### 简单开关与高级枚举并存

基础配置可给人一个清楚的开关，例如“鼠标穿透”。高级模式再显露结构化枚举，例如 `interactive`、`passthrough`、`regions`，最后一种包含受限命名区域。基础设置应映射到同一高级类型；不存在另一套互相打架的布尔状态。高级值、窗口 revision、宿主支持能力和原生生效回执都需要在快照中可见。

相同模式也适用于 Shell：新手只选“显示在任务栏”；熟练提供者可进一步描述任务栏、Alt+Tab、托盘请求和通知策略。所有高权能项默认关闭，由本地用户按世界授权。

### 语音：显式的一次性会话，不是隐形常驻监听

Windows 系统可提供文本朗读和语音识别能力，WinCraft 可把它们设计成可选宿主服务：例如用户点“语音输入”，宿主开始一个有时限、可取消、带录音状态提示的麦克风会话，再将识别文本交给当前提供者；朗读则由宿主用系统语音引擎播报经过声明式组件表达的文本。

麦克风访问必须由本地用户主动开始。默认不监听、不把音频流交给任意 provider、不将音频写入宿主业务存储；优先只提供用户确认过的识别文本。正式接入前要验证 Windows SDK/API、Tauri/WebView2 组合、权限提示、语言支持、设备缺失和取消/超时路径。

## 捕获策略与微信现场观察

屏幕捕获排除可作为每个世界的高级选项，但它只是 Windows 对部分系统捕获途径的显示策略，不是内容保密保证。微软明确说 `SetWindowDisplayAffinity` 不能保证阻止所有捕获，也不能防止拍摄实体屏幕。[SetWindowDisplayAffinity](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity)

2026-10-26 对当前微信窗口做了只读观察：窗口截图接口返回了黑色画面，UI Automation 仍能读取到结构化界面树。没有保存截图或对话文字。**这只是该窗口、该捕获路径下的一次观察；根因尚未确认，不能据此断言微信调用了 `SetWindowDisplayAffinity`。**后续要对照 Windows.Graphics.Capture、桌面级捕获、窗口是否最小化/遮挡及应用策略分别测试，再决定该例能证明什么。

因此该选项应默认关闭，由本地用户逐世界显式启用；快照标明“已请求/原生已应用/不支持/失败”。不能让提供者悄悄对屏幕共享隐藏内容，也不能把捕获排除当成访问控制或安全承诺。

## 面向人工程序与 Agent 的熟练提供者路径

引擎应该像 Minecraft 一样逐层引入能力，而不是把所有 Windows 选项塞进第一课：

1. **入门方块**：用 Python 客户端连接、声明组件、推送数据、处理一个按钮回执；无需 HTML/JS。
2. **红石与事件**：订阅受限的窗口变化、用明确动作响应、处理事件次序与断线；附可运行的最小示例。
3. **高级窗口机制**：锚定、动作轨迹、Shell 曝光、主题枚举和区域输入；先读宿主能力表，再选择兼容分支。
4. **数据包式定制**：受约束的主题包、可复用配方和组合工作区；宿主保留签名/校验、权限提示和回滚。

人工编写的 Python 程序与 Agent 使用同一协议、同一所有权规则和同一事件语义。示例应有开箱即用的 Python 实现、能力降级处理、模拟器/验收说明和常见故障；Agent skill 再教它们按课程建立提供者，不另造一份隐藏协议。

## 依赖顺序与验收门

| 顺序 | 目标 | 先行证明 |
|---|---|---|
| 1 | 定义事件源、订阅与取消、顺序/因果字段和慢消费者行为 | 移动/显隐事件不丢失也不循环；读者订阅不获得写权；断线后订阅失效 |
| 2 | 实现语义锚定、用户几何交接、隐藏/恢复及受限前台请求 | 多屏/DPI、Alt+Tab、系统拒绝聚焦和宿主救援都记录真实结果 |
| 3 | 实现预设主题、Shell 曝光策略与基础/高级枚举 | 任务栏与 Alt+Tab 组合逐一测试；不支持的平台明确回退 |
| 4 | POC 区域命中、AppBar、DWM 外观、捕获排除、语音 | 每项独立权限、平台/版本能力、取消/恢复流程与安全说明 |
| 5 | 临时窗口组、Agent 课程和主题配方 | 多世界移动/隐藏保持租约与权限隔离；真实 Python 示例和 Agent skill 完整走通 |

不应为了“像 Minecraft 一样可玩”而一次开放全部宿主权限。逐个能力从声明、权限提示、原生执行、回执到失败恢复形成闭环后，再进入下一类。

## 官方 Windows 参考

- [Window Features](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features)：窗口状态、层叠透明、尺寸/位置和窗口关系。
- [Extended Window Styles](https://learn.microsoft.com/en-us/windows/win32/winmsg/extended-window-styles)：Tool Window、App Window、No Activate、Topmost 等角色。
- [SetWindowPos](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowpos)：尺寸、坐标、Z 顺序与激活行为。
- [WM_NCHITTEST](https://learn.microsoft.com/en-us/windows/win32/inputdev/wm-nchittest) 与 [RegisterHotKey](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)：区域命中与系统快捷键。
- [DWM window attributes](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/nf-dwmapi-dwmsetwindowattribute)：非客户区和系统合成属性。
- [Notification area](https://learn.microsoft.com/en-us/windows/win32/shell/notification-area) 与 [AppBars](https://learn.microsoft.com/en-us/windows/desktop/shell/application-desktop-toolbars)：托盘和屏幕边缘停靠。
- [UI Automation](https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32)：系统级无障碍与自动化。
