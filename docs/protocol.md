# WinCraft 协议 0.3

此协议为本原型设计，不宣称实现 JSON-RPC 2.0、Adaptive Cards 或 A2UI。机器约束见 `protocol/request.schema.json`、`protocol/scene.schema.json` 与 `protocol/theme.schema.json`。Runtime 另检查节点数量、深度、重复 ID、主题对比度、权限和版本。

当前线协议版本为 `0.3`。客户端与 host 在 `hello` 中严格比较版本；0.2 增加 provider 可配置的 `title_bar_visible` 和按钮/输入的静态 `context_action`，0.3 增加可配置的 `text_selectable` 窗口默认值。0.3 的后续 host 可以通过 `host.capabilities` 增加**可选**渲染能力；客户端必须先核对能力表，缺失时给出明确错误，不可直接发送新组件或 scene feature。当前可选能力包含 `textarea`、按钮 `shortcut: "escape"`、`selection_groups` 与 scene-level `theme_tokens`，不会改变旧 0.3 客户端发送的场景。旧协议版本不兼容时会返回 `PROTOCOL_MISMATCH`。

## 发现与传输

启动生成实际端口和每次启动不同的 host token，写到 `<app-local-data>/runtime/<host-id>.runtime.json`。本机原生提供者读该文件，不能猜默认端口。

`GET /health` 不鉴权，只返回 readiness、协议、host_id、是否有 native backend，不暴露世界内容。

`GET /v1/discovery` 和 `GET /v1/ws` 必须带 `Authorization: Bearer <token>`。首版拒绝包含 Origin 的请求，避免任意网页借访问本机服务取得权限；浏览器扩展原生接入与 origin 白名单属于后续功能。

`world.list` 只列出当前 session 已加入的世界与显式允许 `open_authenticated` 加入的非系统世界；未加入的 `invite` 世界不会向其他 session 暴露 ID、标题或 writer 元数据。本地 operator 可枚举全部世界。列出开放世界仍不授予 snapshot/read/write：必须再调用 `world.join`，邀请世界还要提供 join key。列表含世界 ID，显示名相同的不同实例保持为独立条目。

WebSocket 连上后 5 秒内发送 hello。只有 protocol=0.3 会成功；返回服务端生成的 session_id 与能力表。新客户端在创建世界前检查 `ready.capabilities.components`、`keyboard_shortcuts`、`button_features` 与 `scene_features`；旧 host 未列出的能力必须明确报错。未支持的能力返回 false 或列在 not_implemented，不能悄悄把不支持当成功。

```json
{"id":"hello-1","method":"hello","params":{"protocol":"0.3","provider_name":"python.example"}}
```

## 消息封套

请求：`{id, method, params}`。成功：`{id, ok:true, result}`。失败：`{id, ok:false, error:{code,message}}`。id 只负责请求关联，**不是幂等键**。发生响应超时不能盲目重放写操作；先读回状态，必要时重新建立会话/租约。

推送消息使用 `event` 字段，与请求回复区分。

## 方法

| 方法 | 权限/主要参数 | 结果 |
|---|---|---|
| session.ping | 当前连接 | 续期尚未过期的自有租约 |
| host.capabilities | 已鉴权连接 | 协议、能力与资源限制 |
| world.list | 已鉴权连接 | 当前 session 已加入的世界与非系统 `open_authenticated` 世界；仅元数据，不返回完整 scene |
| world.create | window?, join_policy?, claim? | 世界快照、加入凭证、可选写租约 |
| world.join | world_id, mode, join_key? | 读成员资格，或独占写租约 |
| world.snapshot | 已加入，或本地操作员 | 当前完整快照 |
| world.leave | 当前成员 | 退出并释放自身写租约 |
| lease.renew | world_id + lease | 延长有效租约 |
| lease.release | world_id + lease | 释放写权；读成员关系可保留 |
| scene.replace | 写租约 + expected_revision + scene | 原子替换整个 scene |
| scene.patch | 写租约 + expected_revision + ops | 原子增删替换移动/属性更新 |
| data.replace | 写租约 + expected_revision + data | 替换 scene.data，不改变结构 |
| window.configure | 写租约 + expected_revision + patch | 更新期望窗口属性，native ack 单独报告 |
| action.result | 写租约 + event_id + ok + message? | 确认/拒绝一条实际交互 |
| event.subscribe | 已加入世界 + world_id + types | 注册本连接的窗口状态订阅；读成员无需写租约 |
| event.unsubscribe | subscription_id | 幂等注销本连接的订阅 |
| world.destroy | 写租约 | 销毁世界；读成员收到删除事件 |

不存在网络 operator/rescue、shell、eval、文件读写、加载 URL 或任意 Win32 调用方法。内部管理器的操作员权限只能由宿主创建，不能通过 hello 自报获取。

## Scene 与组件

Scene 为 `{root, data, theme?}`。Node 为 `{id, kind, props?, children?}`。当前支持 stack、row、text、metric、progress、badge、button、input、textarea、key_value、divider。容器只有 stack/row；叶子不能含 children。`textarea` 是可选的多行文本输入能力，含 `label`、`value`、`action`、`placeholder`、`disabled`、`submit_label`、可选 `context_action`，以及可选的 `shortcut: "ctrl_enter"` / 静态 `shortcut_action`；Renderer 限制 8192 个 UTF-16 code units，协议动作上限为 32768 UTF-8 bytes。未获得 `components` 中的 `textarea` 能力时不得发送该节点。

`theme` 只在 host 宣告 `scene_features: ["theme_tokens"]` 时可用，字段严格限于 `background`、`foreground`、`accent`、`font_scale`、`radius_px` 与 `spacing_px`，完整结构见 [`theme.schema.json`](../protocol/theme.schema.json)。颜色为 `#RRGGBB`；宿主额外检查前景/背景和强调色/背景对比度，拒绝任意 CSS、HTML、脚本、远程资源与未知 token。无效主题让本次 scene 更新原子失败，原 scene、revision、业务数据和租约保持不变。主题只作用于内容区域；标题栏、来源身份、状态、权限提示和本机接管界面由宿主控制。系统高对比、减少动画以及本机字体缩放优先于 provider token；字体缩放快捷键为 Ctrl+Shift+加号、Ctrl+减号，Ctrl+0 重置为主题字号。主题不改变任何业务状态或动作权限。

组件 ID 全世界唯一，1–64 个 ASCII 字母数字或 `_-.:`，用于稳定渲染和动作定位。props 由组件白名单定义。`action` 必须是静态字符串，不能动态绑定成任意宿主方法。

`button`、`input` 与 `textarea` 可选注册静态 `context_action`。WinCraft 默认阻止 WebView 原生右键菜单；只有声明了该属性的控件才会在右键时向当前写者发送对应交互。按钮值为 `null`，输入控件值为当前文本。未注册时右键不触发业务动作。该属性只选取提供者声明的动作，不加载脚本或原生菜单。

按钮可选注册 `shortcut: "escape"` 与独立静态 `shortcut_action`，每个世界最多一个；textarea 可注册 `shortcut: "ctrl_enter"` 与独立 `shortcut_action`，同样每个世界最多一个。host 必须分别在 `keyboard_shortcuts` 宣告这些固定快捷键。鼠标点击使用 `action`，快捷键使用 `shortcut_action`。输入法组合期间忽略快捷键；它们不等同于 OS 级全局快捷键，也不授予宿主权限。

选项按钮可组成静态 `selection_group`，指定一致的 `selection_mode: "single" | "multiple"` 和布尔 `pressed` 状态。单选组最多一个 pressed 项。Renderer 为每组维护一个 Tab 停靠点；方向键移动焦点，单选组同时请求选中项，空格继续触发当前选项。未设置此组语义的按钮保留普通 Tab 行为。只有 host 宣告 `button_features: ["selection_groups"]` 时才能使用。

原生 Windows host 可额外宣告 `external_window_actions`。按钮可以声明宿主登记的应用 ID（当前 `obsidian`、`traffic_monitor`）、枚举操作（`activate`、`maximize`、`restore`、`minimize`）与有界标题子串；用户点击后由宿主操作已存在的匹配窗口，再把动作交给提供者确认。宿主不启动外部应用、不执行提供者命令，也不接受任意可执行路径。headless host 不宣告该能力。`native_window_action` 是可扩展的宿主窗口服务，只用于跨应用窗口；WinCraft 世界本身仍通过 `window.configure` 管理。添加新动作必须保持类型化、有限、由本地用户交互触发并返回原生结果。

属性值可用 `{"$path":"/focus/remaining"}` 读取 JSON Pointer 数据。没有表达式、循环脚本、网络读取、HTML 或 CSS 注入。复杂业务计算留给提供者。key_value 接收 `{key,value}` 列表，首版最多渲染 64 行。

## 动态结构操作

`insert(parent,index,node)`、`remove(node_id)`、`replace(node_id,node)`、`move(node_id,parent,index)`、`props(node_id,props)`。

move 的 index 按**移除原节点之后**的目标 children 解释。不可移除/移动根，不能移入自身后代。props 为浅层覆盖；要彻底移除一个属性可 replace 节点。所有操作先在克隆上执行，验证整个结果后提交；任一步失败保留原 scene/revision。

## 原生窗口与版本

width/height 为逻辑像素；position 为桌面物理像素，允许负坐标。`surface_opacity` 控制透明原生窗口内整块 renderer surface 的视觉不透明度，默认 `0.8`；快照可读，写租约持有者可用 `window.configure` 更新，取值范围 `0.15..=1.0`。它不改变 OS 原生窗口的透明/命中测试能力。

新窗口默认采用 `geometry_control=human` 且 `resizable=true`，本地用户可拖动窗口边缘调整宽度。横向调整不关闭内容高度适配；renderer 在当前原生宽度下重测高度，宿主保留用户宽度。`geometry_control` 控制尺寸所有权：`human` 时 provider 不能配置 width/height，`provider` 时 Tauri 不开放边缘 resize。

位置所有权与尺寸所有权可分开。新增的可选 `position_control` 必须先确认 host capability `window_properties` 含 `position_control`；未设置时继承 `geometry_control`，保持旧 provider 行为。`geometry_control=provider, position_control=human, resizable=false` 表示 provider 可切换窗口尺寸模式，但本地用户仍可移动窗口；实际移动更新 snapshot 的 position，不改 provider 尺寸。provider 仅在 `position_control=provider` 时可以配置 position/anchor。无标题栏时，`background_drag_enabled=true` 允许普通、非文本、非交互背景作为拖动抓手；按钮、输入、链接、文本或已选中文本不触发移动。穿透或位置控制归 provider 时拖动仍失败关闭。

provider 位置控制可选择提供 `anchor` 代替固定 `position`：`corner` 为 `top_left`、`top_right`、`bottom_left`、`bottom_right` 之一，`margin_x` / `margin_y` 是逻辑像素边距。宿主相对于当前解析显示器的 work area 乘 scale factor 换算为物理桌面坐标，并把窗口夹在可用工作区内；尺寸大于工作区时回到工作区左/上起点。anchor 与 position 同时提供时 anchor 优先。人类移动时宿主将实际 position 写回并清除 anchor；provider 位置控制下配置 position/anchor，或人类位置控制下配置它们，均返回 `HUMAN_GEOMETRY`。本地 rescue 清除 anchor、恢复人类位置控制并撤销 writer lease。Tauri 会在 ScaleFactorChanged 时重新解析；Windows 显示器拔除自动迁移仍待原生验收。

snapshot 中 revision 对应已接受的世界投影，sequence 对应所有快照变化，window_revision 对应原生意图，lease.epoch 对应写权限世代。具体字段见 architecture.md。

成功响应 window.configure 只证明“接受”，不是“Windows 已执行”。读取 native.state/applied_window_revision/error 判断兑现状态。headless 明确为 unavailable。

窗口默认 `visible=true`。设置 `visible=false` 只隐藏原生窗口，不销毁世界或撤销写租约；当前 writer 可从后续 snapshot 观察该值，并通过带 lease 与 expected_revision 的 `window.configure` 恢复 `visible=true`。本地标题栏最小化和管理器显示/隐藏操作走可信 operator 路径；关闭按钮销毁普通世界，语义不同。

标题栏默认 `title_bar_visible=true`，并停留在内部滚动工作区之外；provider 可在 `window.configure` 中切换它。默认 `click_through=false`；显式启用后鼠标事件穿过窗口，按钮也无法直接点，provider 可恢复，操作员可通过管理器接管。隐藏标题栏或穿透状态下，优先用管理器“接管并找回”恢复本地操作能力。

文本默认可选中：`text_selectable=true`，provider 可在 `window.configure` 中读写该窗口级默认值。设置为 false 后，窗口内容默认不可选；具体组件样式仍可显式覆盖其文本选择行为。标题栏及其子元素始终不可选中。组件协议不接受任意 CSS/脚本，覆盖规则由宿主 renderer 的组件样式实现。

有自定义标题栏时，标题区域单击（未超过拖动阈值）在本机折叠/展开下方内容；这不改变 scene、world 或 lease。托盘“暂时隐藏全部窗口/显示全部窗口”是宿主本地的临时可见性覆盖：保留各 world 的 `window.visible` 与 provider 租约，恢复时只显示覆盖前逻辑可见且之后仍可见的窗口。正常 `online` 的 host 状态行与 provider 空状态 badge 不展示；连接异常/来源过期状态仍可见。

Windows 虚拟桌面 pinning 不属于当前 0.3 窗口属性。用户已决定默认当前桌面、provider 可选择“所有桌面”，但 Tauri/tao 的公开 `visible_on_all_workspaces` API 在 Windows 标注为 unsupported；不能先接受该字段再报告成功。实现边界与待决定方案见 `docs/windows.md`。

## 交互

WebView 通过 caller-bound Tauri IPC 携带 node_id、value、expected_revision。宿主验证当前组件与版本后生成 event ID，从当前 scene 读取 action，向当前写入者发送：

```json
{"event":"interaction","data":{"id":"33333333-3333-4333-8333-333333333333","world_id":"11111111-1111-4111-8111-111111111111","component_id":"pause","action":"toggle_pause","value":null,"lease_epoch":1,"revision":3}}
```

提供者执行业务、更新数据，再提交 action.result。pending 超时为 10 秒。断线/撤销会将未完成动作标为错误。旧写入者不能确认新租约的动作。

## 推送和背压

`world.snapshot` 仅向有读资格的会话发送；`interaction` 仅向当次写入者；`world.deleted` 发给原成员。UI 首次监听建立后读取快照，使用 sequence 拒绝晚到旧快照。

`event.subscribe` 只对当前 session 已加入的世界有效，最多注册 32 个会话级订阅；离开/销毁世界或断开连接时自动清理。当前只支持 `window.geometry_changed` 与 `window.visibility_changed` 两种 `delivery:"state"` 事件。事件含 event/subscription/world ID、world `sequence`、`window_revision`、来源和可选 `cause_id`，payload 只含最新窗口状态；几何事件携带物理 `position` 或语义 `anchor`，尺寸为逻辑像素。读取者可订阅，但订阅本身不会授予加入、写租约或任何动作权限。

状态事件可以合并；序号有间隔是合法的，接收方应采用最新状态，不能要求每一帧拖动都送达。`cause_id` 是造成该快照变化的直接请求或内部交互 ID，不是幂等键。`interaction` 仍是独立的 occurrence 通道，不能静默丢弃；广播滞后时服务端发 `resync_required` 并断开，提供者需重连、重新加入并重建。状态事件只通知观察者，宿主没有自动事件→动作规则。

事件封套的正反例见 [`event.schema.json`](../protocol/event.schema.json) 与 [`examples/window-events.json`](../protocol/examples/window-events.json)。

业务投影仍通过完整快照而非通用 scene/data 差分传输。窗口状态变更走 per-world latest-value watch，因此可合并中间状态；交互与删除 occurrence 使用容量 256 的独立广播队列。occurrence 队列发生 lag 时服务端发 `resync_required` 后断开，避免悄悄漏掉交互。两条通道都不是无损持久事件流，不承诺断线动作重放或 exactly-once 业务执行。

## 错误重点

FORBIDDEN、WRITE_CONFLICT、STALE_LEASE、LEASE_EXPIRED、OPERATOR_HOLD、REVISION_CONFLICT、HUMAN_GEOMETRY、INVALID_SCENE、INVALID_PATCH、NOT_FOUND、LIMIT、ACTION_TIMEOUT、ACTION_FINISHED、PROTOCOL_MISMATCH。

协议 schema 与 Rust 类型可能存在边角约束差异，必须通过真实服务正反例验收。离线 schema 通过不是服务实现通过。
