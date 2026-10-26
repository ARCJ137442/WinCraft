# WinCraft 协议 0.3

此协议为本原型设计，不宣称实现 JSON-RPC 2.0、Adaptive Cards 或 A2UI。机器约束见 `protocol/request.schema.json` 与 `protocol/scene.schema.json`。Runtime 另检查节点数量、深度、重复 ID、权限和版本。

当前线协议版本为 `0.3`。客户端与 host 在 `hello` 中严格比较版本；0.2 增加 provider 可配置的 `title_bar_visible` 和按钮/输入的静态 `context_action`，0.3 增加可配置的 `text_selectable` 窗口默认值。旧版本不兼容时会返回 `PROTOCOL_MISMATCH`。

## 发现与传输

启动生成实际端口和每次启动不同的 host token，写到 `<app-local-data>/runtime/<host-id>.runtime.json`。本机原生提供者读该文件，不能猜默认端口。

`GET /health` 不鉴权，只返回 readiness、协议、host_id、是否有 native backend，不暴露世界内容。

`GET /v1/discovery` 和 `GET /v1/ws` 必须带 `Authorization: Bearer <token>`。首版拒绝包含 Origin 的请求，避免任意网页借访问本机服务取得权限；浏览器扩展原生接入与 origin 白名单属于后续功能。

WebSocket 连上后 5 秒内发送 hello。只有 protocol=0.3 会成功；返回服务端生成的 session_id 与能力表。未支持的能力返回 false 或列在 not_implemented，不能悄悄把不支持当成功。

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
| world.list | 已鉴权连接 | 仅世界元数据，非完整 scene |
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
| world.destroy | 写租约 | 销毁世界；读成员收到删除事件 |

不存在网络 operator/rescue、shell、eval、文件读写、加载 URL 或任意 Win32 调用方法。内部管理器的操作员权限只能由宿主创建，不能通过 hello 自报获取。

## Scene 与组件

Scene 为 `{root, data}`。Node 为 `{id, kind, props?, children?}`。10 种 kind：stack、row、text、metric、progress、badge、button、input、key_value、divider。容器只有 stack/row；叶子不能含 children。

组件 ID 全世界唯一，1–64 个 ASCII 字母数字或 `_-.:`，用于稳定渲染和动作定位。props 由组件白名单定义。`action` 必须是静态字符串，不能动态绑定成任意宿主方法。

`button` 与 `input` 可选注册静态 `context_action`。WinCraft 默认阻止 WebView 原生右键菜单；只有声明了该属性的控件才会在右键时向当前写者发送对应交互。按钮值为 `null`，输入框值为当前文本。未注册时右键不触发业务动作。该属性只选取提供者声明的动作，不加载脚本或原生菜单。

属性值可用 `{"$path":"/focus/remaining"}` 读取 JSON Pointer 数据。没有表达式、循环脚本、网络读取、HTML 或 CSS 注入。复杂业务计算留给提供者。key_value 接收 `{key,value}` 列表，首版最多渲染 64 行。

## 动态结构操作

`insert(parent,index,node)`、`remove(node_id)`、`replace(node_id,node)`、`move(node_id,parent,index)`、`props(node_id,props)`。

move 的 index 按**移除原节点之后**的目标 children 解释。不可移除/移动根，不能移入自身后代。props 为浅层覆盖；要彻底移除一个属性可 replace 节点。所有操作先在克隆上执行，验证整个结果后提交；任一步失败保留原 scene/revision。

## 原生窗口与版本

width/height 为逻辑像素；position 为桌面物理像素，允许负坐标。`surface_opacity` 控制透明原生窗口内整块 renderer surface 的视觉不透明度，默认 `0.8`；快照可读，写租约持有者可用 `window.configure` 更新，取值范围 `0.15..=1.0`。它不改变 OS 原生窗口的透明/命中测试能力。

新窗口默认采用 `geometry_control=human` 且 `resizable=true`，本地用户可拖动窗口边缘调整宽度。横向调整不关闭内容高度适配；renderer 在当前原生宽度下重测高度，宿主保留用户宽度。提供者必须显式切到 `provider` 几何模式才可提交坐标/尺寸，该模式不接受人工 resize。

snapshot 中 revision 对应已接受的世界投影，sequence 对应所有快照变化，window_revision 对应原生意图，lease.epoch 对应写权限世代。具体字段见 architecture.md。

成功响应 window.configure 只证明“接受”，不是“Windows 已执行”。读取 native.state/applied_window_revision/error 判断兑现状态。headless 明确为 unavailable。

窗口默认 `visible=true`。设置 `visible=false` 只隐藏原生窗口，不销毁世界或撤销写租约；当前 writer 可从后续 snapshot 观察该值，并通过带 lease 与 expected_revision 的 `window.configure` 恢复 `visible=true`。本地标题栏最小化和管理器显示/隐藏操作走可信 operator 路径；关闭按钮销毁普通世界，语义不同。

标题栏默认 `title_bar_visible=true`，并停留在内部滚动工作区之外；provider 可在 `window.configure` 中切换它。默认 `click_through=false`；显式启用后鼠标事件穿过窗口，按钮也无法直接点，provider 可恢复，操作员可通过管理器接管。隐藏标题栏或穿透状态下，优先用管理器“接管并找回”恢复本地操作能力。

文本默认可选中：`text_selectable=true`，provider 可在 `window.configure` 中读写该窗口级默认值。设置为 false 后，窗口内容默认不可选；具体组件样式仍可显式覆盖其文本选择行为。标题栏及其子元素始终不可选中。组件协议不接受任意 CSS/脚本，覆盖规则由宿主 renderer 的组件样式实现。

## 交互

WebView 通过 caller-bound Tauri IPC 携带 node_id、value、expected_revision。宿主验证当前组件与版本后生成 event ID，从当前 scene 读取 action，向当前写入者发送：

```json
{"event":"interaction","data":{"id":"33333333-3333-4333-8333-333333333333","world_id":"11111111-1111-4111-8111-111111111111","component_id":"pause","action":"toggle_pause","value":null,"lease_epoch":1,"revision":3}}
```

提供者执行业务、更新数据，再提交 action.result。pending 超时为 10 秒。断线/撤销会将未完成动作标为错误。旧写入者不能确认新租约的动作。

## 推送和背压

`world.snapshot` 仅向有读资格的会话发送；`interaction` 仅向当次写入者；`world.deleted` 发给原成员。UI 首次监听建立后读取快照，使用 sequence 拒绝晚到旧快照。

首版使用完整快照而非最小差分。广播缓冲 256 条；慢消费者发生 lag 会得到 resync_required 后断开，避免悄悄漏掉交互。它不是无损持久事件流，不承诺断线动作重放或 exactly-once 业务执行。

## 错误重点

FORBIDDEN、WRITE_CONFLICT、STALE_LEASE、LEASE_EXPIRED、OPERATOR_HOLD、REVISION_CONFLICT、HUMAN_GEOMETRY、INVALID_SCENE、INVALID_PATCH、NOT_FOUND、LIMIT、ACTION_TIMEOUT、ACTION_FINISHED、PROTOCOL_MISMATCH。

协议 schema 与 Rust 类型可能存在边角约束差异，必须通过真实服务正反例验收。离线 schema 通过不是服务实现通过。
