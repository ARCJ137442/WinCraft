# 架构与系统不变量

```text
外部提供者（Python / 应用插件 / Agent；无需前端源码）
        │ 鉴权、hello、声明/数据/操作回执
        ▼
Rust Axum 服务 ── Hub ── Engine（唯一运行时裁决）
                         │ 世界、租约、scene、窗口意图
          ┌──────────────┴─────────────────┐
          ▼                                ▼
Tauri 原生窗口适配器                 内部管理提供者
创建、位置、穿透、显隐                 构造普通组件树
          │                                │
          └────── 通用 WebView renderer ◄───┘
                         │ 用户动作
                         └── 受限 IPC → Engine → 当前写入者
```

## 分层

`wincraft-core` 不依赖 Tauri、HTTP 或 WebView，可独立测试。它决定谁有权修改哪个世界、版本是否正确、场景是否有效。

`wincraft-server` 给核心增加连接身份、JSON 消息、鉴权、限额、事件和提供者通道。headless 使用同一个核心，而不是 Python/JS 重写模型。

状态变更通过 per-world latest-value watch 推送完整快照，几何/逻辑显隐的类型订阅从相邻快照计算并允许合并；交互和删除等 occurrence 走独立有界广播，队列滞后时显式重同步并断开。订阅只对本连接已加入的世界有效，不授予写租约，断线即清理。

`apps/desktop/src-tauri` 负责真实窗口，将已接受的窗口意图应用到系统。它不能决定外心是否暂停。通过受限的 caller-window IPC 接收交互，不允许某个渲染器指定另一个世界的 ID。

托盘全局 hide/show 是独立于每个 `WindowSpec.visible` 的临时 host overlay：hide 时记住逻辑可见的 world IDs，native windows 隐藏但 scene、lease 和 provider 偏好不变；show 只恢复这些仍保持 `visible=true` 的世界。单窗最小化仍通过 `visible` 进入快照，provider 可观察和恢复。标题栏点击折叠只影响 renderer 展示高度，不触碰 Rust 世界状态。

Tauri tray Exit 与 headless Ctrl+C 共用 `RunningServer::shutdown()`：停止接受新连接，向 WebSocket 客户端发送关闭信号，撤销并断开普通 provider session，停止 housekeeping/listener 任务，再删除当前宿主拥有的 runtime descriptor。`Drop` 保留 abort 兜底；异常强杀仍可能留下一份失效 descriptor，不能把它当作正在运行的 host。

`apps/desktop/src` 只负责可信组件渲染。相同组件树在外部世界和管理器中使用相同代码。用户提供的数据不会成为 HTML、JS 或任意 CSS。`WindowSpec.text_selectable` 随快照进入 renderer，控制整个窗口内容的默认文本选择；宿主组件样式可对单个元素覆盖，公共标题栏始终不可选。

`Scene.theme` 是经能力表声明的可选 token 对象；Rust 验证格式、边界和颜色对比度，renderer 只将安全值应用到内容容器。自定义标题栏、Provider 身份、连接状态、权限提示与接管入口保持 host-controlled。系统 forced-colors/reduced-motion 和本机字号缩放优先于 Provider theme；任意 stylesheet、远程资源与脚本不进入协议。

宿主 chrome 与内部管理器的静态文案使用共享 `zh-CN` / `en-US` key catalog。语言是本机 host UI 偏好，不是线协议字段；管理器通过普通内部提供者动作切换，偏好写入仅包含 locale ID 的本机 `ui-locale.txt`，其他打开的 WebView 接收 `host/locale` 更新。外部 Provider 的题面、选项、消息与业务数据保持来源语言，Renderer 不自动翻译这些值。

## 四个版本号，不能混用

| 字段 | 含义 |
|---|---|
| lease.epoch | 写权限世代；撤销/转移后旧消息失效 |
| revision | 业务投影和窗口意图的版本；写请求必须 expected_revision 一致 |
| sequence | 所有可见快照变化的单调序号，包括动作/native 回执；解决首次读取与推送竞态 |
| window_revision | 只有窗口意图/原生人类几何变化才递增；数据刷新不能反复调用原生设置 |

原生应用完成后的回执只推进 sequence，不应使业务写入因为一个无关 native ack 失去 revision。

## 关键不变量

1. 同一世界最多一个有效写租约。
2. 除明确的本地操作员路径，修改必须同时匹配服务端会话、lease ID、epoch 和有效期。
3. 读者得到复制的快照，不能拿到写令牌。
4. 列出窗口不是加入授权；受邀窗口必须持加入凭证。
5. 动态结构更新先在副本上执行和验证，再一次提交。
6. UI 动作来自已接受 scene 中的静态 action ID，不接受调用者伪造任意 action。
7. 业务是否完成由提供者决定；Host 只维护 pending/ack 的协议状态。
8. 原生调用失败独立报告；不能抹掉失败或伪装成已兑现。
9. 数据刷新不得重置用户手动移动后由原生层观测到的位置。
10. 用户接管立即 fence 旧租约，并阻止自动再次占用，直至解除。
11. 无 business 数据库、无永久窗口—提供者关系；新宿主启动获得新世界 ID。
12. 原生窗口与管理器的职责不要求一窗一进程或一提供者一 WebView。

## 隔离边界

每个世界独立组件树、权限与动作路由，一个 WebView 对应一个世界，不因多接入一个提供者就新增一个 WebView。共享宿主仍有共同故障域；Tauri/WebView2 可能有多个系统进程，不能称为“全应用只有一个进程”。

首版不允许第三方执行渲染代码，不提供插件代码沙箱。未来放开自定义组件包必须重新进行代码加载与隔离设计。

## 重建路径

提供者连接宿主 → 协商协议 → 发现/创建世界 → 取得租约 → 发送完整 Scene → 增量更新 → 断线后旧租约作废。恢复时重新加入/申请，新会话不能沿用旧 lease。若原世界仍受邀请保护，提供者需保留或重新获得加入凭证；宿主不假装记得它。

窗口外观也是可重建的运行状态：provider 从快照读取 `text_selectable`，通过受 lease 与 revision 检查的 `window.configure` 更新它。Tauri renderer 将值投影为 CSS 窗口默认；组件选择器仍可针对文本组件设置明确的覆盖样式。协议不接收 provider 提交的任意 CSS。
