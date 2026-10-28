# ExoMind 工作台只读投影原型

## 目标与边界

examples/python/exomind_workbench.py 是一个读取 ExoMind 当前活动时间块的 WinCraft provider 原型。ExoMind RT 仍是时间块状态的唯一真相源；provider 只调用 GET /timeblocks/active，不读取任务列表或 eventlog，也不调用时间块暂停、恢复、结束、开始、任务写入或档案迁移接口。

窗口中的“收起/展开”和“隐藏浮窗”只改变本地 WinCraft 显示状态。紧凑切换分两步写入 WinCraft：先替换 scene，再通过 window.configure 请求对应尺寸；如果尺寸请求失败，provider 对该动作回 ok=false 并说明 scene 已更新但尺寸未确认，不声称两步是原子操作。暂停、继续和结束仍由 ExoMind 原程序执行；此原型没有为它们注册动作。

用户可以使用真实外心档案做运行联调。单元测试中的 fixture 是脱敏合成结构，只验证解析、投影和请求方法，不能当作实时 RT 或 Tauri 验收证据。

## 与来源工作台的对照

本原型基于用户提供的 ExoMind 源码进行只读行为研究。公开文档仅保留可迁移的窗口行为，不记录本机源码路径、档案标识、实时档案状态、时间块内容或 RT 构建标识。观察到的交互形态包括全尺寸/紧凑布局、临时隐藏与恢复、不可手动 resize、内容区拖动及按当前内容测量尺寸；这些是来源工作台的行为参考，不表示本原型已全部复刻。

WinCraft 侧的计时投影只由提供者从允许读取的活动时间块响应派生，并且不会向 ExoMind 写回推算结果。真实字段及版本差异须在获得许可的本地验收中核对，不进入公开证据。

### 外心源码行为与 WinCraft 原型的范围

| 项目 | ExoMind 工作台 | WinCraft 原型 |
|---|---|---|
| 状态/模式 | ExoMind 区分 running 单卡、running mini、mini-peek 及 idle bubble；mini-peek 由指针悬停展开 | WinCraft 用 full、compact、mini 三档本地展示；idle 是内容状态，可与任一展示档位组合。host 不提供 hover 事件时，用户通过本地按钮切换 |
| full | 单卡来源回退尺寸 390×192；状态/名称在上，计时与来源操作在下；挂载后按可见卡片测量 | 请求 390×192 fallback；保留状态、时间块名称、计时及只读说明，仅有本地“收起/隐藏”操作 |
| compact | mini-peek 来源回退尺寸 352×200；可见 pill 的 CSS 宽度类为 328 px，展开后显示暂停/结束操作 | 请求 328×160 本地尺寸估值；状态、名称和计时仍可见，以只读说明替代外心写操作 |
| mini | 来源窗口回退尺寸 248×120；收起 pill 的 CSS 宽度类为 224 px；挂载后按可见 pill 测量 | 请求 248×120 来源 fallback；显示时钟、状态、名称、“只读”标记及本地展开/隐藏入口 |
| idle | 无活动时间块时显示 idle bubble；该 UI 可进入外心配置/开始流程 | 只显示空闲状态和说明，不提供开始按钮，也不伪造计时。开始仍由用户在外心原程序完成 |
| 数据源 | ExoMind RT 的活动时间块与 ExoMind 自己的 profile 选择 | 仅使用本次明确指定 profile 的 active-timeblock GET；不从 host 推断档案 |
| 拖动 | data-tauri-drag-region 内容抓手；窗口不可手动 resize | 请求隐藏标题栏、背景可拖动、provider 尺寸、人类位置；依赖 position_control 能力 |
| 隐藏/恢复 | ExoMind 本地状态隐藏，主程序可恢复 | WinCraft 本地 window.configure visible=false，由 WinCraft 管理器恢复 |
| 外心操作 | 暂停/继续/结束/开始由外心 UI 处理并更新业务状态 | provider 不注册或发送这些动作；只允许 `wincraft.display.next` 与 `wincraft.display.hide` 两个 WinCraft 本地动作 |
| 外观 | 截图与源码中的卡片视觉 | 受限 theme_tokens + WinCraft surface opacity 0.8；不传 CSS、HTML 或脚本 |
| 虚拟桌面 | 当前 overlay source 未发现“所有桌面显示” API | 不请求跨虚拟桌面能力 |

### 行为验收场景

- **Given** 成功 GET 返回合成活动时间块，**When** 本地用户连续切换展示档位，**Then** WinCraft scene 依次进入 full → compact → mini → full，并请求各档位的本地 fallback 尺寸，ExoMind 仅收到后续只读 GET。
- **Given** 成功 GET 返回空结果，**When** 渲染 full 或 mini，**Then** 显示空闲状态和回到外心开始计时的说明，不出现空白标题、假计时或开始动作。
- **Given** GET 返回 404 或最近一次读取后连接失败，**When** 渲染任一档位，**Then** 显示“状态待核对”或陈旧/错误来源提示，不能把失败解释为空闲或实时。

#### 尺寸与 scale factor 证据

ExoMind Rust 创建窗口时先给 412×490 的初始尺寸。`NowWorkbenchOverlayPage` 随后按状态选 fallback：full 390×192、mini 248×120、mini-peek 352×200。可见 surface 挂载后，代码读取该元素的 `getBoundingClientRect()`，将 `Math.ceil(rect.width/height)` 作为测量值，并在可用时由 `ResizeObserver` 触发下一帧重测。只有测量键与当前状态相符时，测量结果才覆盖 fallback；随后通过 `setSize(new LogicalSize(width, height))` 调整 Tauri 窗口。这里传入的是逻辑尺寸；来源代码没有手动应用 scale factor，Tauri 原生窗口 API 根据 scale factor 处理逻辑尺寸。Rust 的 `inner_size()` 读取路径用于窗口重新定位，是物理尺寸口径，不能与页面的 CSS 逻辑尺寸混为一谈。

mini 的来源 CSS 宽度类为 224 px，mini-peek 为 328 px；两者高度均由可见 pill 的实际布局决定。源码没有记录一次实际 `getBoundingClientRect()` 的稳态结果，因此只能确认运行时尺寸跟随该 pill，不能用截图反推出确切 CSS 高度。248×120 与 352×200 是来源 fallback，并非稳定测量结果。WinCraft provider 当前只发送静态 `window.configure` 尺寸，没有复刻这条 DOM/ResizeObserver 测量链：mini 的 248×120 仍是未验证 fallback，compact 的 328×160 是本地估值。真实 Windows host 的稳态高度、scale factor 后的物理尺寸及窗口边框尚未测量。截图中的像素大小不作为 CSS 或原生尺寸证据。

WinCraft 组件协议没有 hover 事件，因此不声称复刻了 ExoMind 的自动 mini-peek 展开。真实像素、内容换行、原生尺寸与拖动仍须在 Windows host 核对。

**宿主能力前置条件：**该原型请求 geometry_control=provider + position_control=human，以锁定尺寸同时允许人类移动；这与只有单一 geometry_control 的旧宿主不兼容。provider 在创建世界前检查 window_property:position_control，旧 host 缺少此能力时会失败关闭，不降级成固定位置或可手动 resize 的错误体验。

当前 ExoMind now_workbench_overlay_restore_internal() 每次都回到默认右下位置，而拖动位置会另行持久化；reopenFromMainWindow() 调用 restore，因此“拖动→临时隐藏→从主程序重开仍保留位置”值得作为 ExoMind 自身回归用例。此原型不调用 ExoMind restore/position 写接口。

## 配置与运行

由用户明确提供当前 RT base、profile 和必要认证头；不要猜端口、profile 或认证方式，也不要从聊天应用凭据或其他应用配置推导它们。WinCraft runtime 必须来自本次 host manager/启动输出中的实际路径，不读取或打印 descriptor 内容。

示例（PowerShell）：

    $env:EXOMIND_RT_BASE = '<用户明确选择的 RT base URL>'
    $env:EXOMIND_PROFILE_ID = '<用户明确选择的 profile ID>'
    $env:WINCRAFT_RUNTIME = '<本次 WinCraft manager 显示的实际 runtime descriptor 路径>'
    python examples/python/exomind_workbench.py

若 RT 需要鉴权，可按实际部署设置 EXOMIND_HEADERS_JSON。不要将令牌放入命令行、日志、截图或证据文件。远程 RT 必须使用 HTTPS 或 SSH tunnel；代码拒绝对非回环明文 HTTP 发送凭据。

provider 轮询 GET 的默认间隔为 1 秒，响应上限 128 KiB。HTTP 404 显示为“无活动时间块或端点需要核对”，不据此声称 RT 健康或档案为空。读取失败时，保留最后一次成功显示并标记来源读取失败；首读失败则显示无数据状态，不造出活动块。

按 Ctrl+C 停止 provider 时，它只尝试销毁自己创建的 WinCraft 投影世界；不会向 ExoMind 发送任何写请求。显示档位切换只变更本地 scene 和窗口尺寸，隐藏只变更本地显隐；若 `world.destroy` 结果不确定，应在 WinCraft 管理器中核对这个原型世界，不要盲目重试。

## 本地测试

    python -m unittest discover -s tests -p 'test_exomind_workbench.py' -v

这些用例只使用合成 fixture，覆盖 running/paused 倒计时投影、full/compact/mini 的本地模式循环、idle 与 404/错误区分、active 路由 GET 方法、profile 显式绑定、远程明文 HTTP 拒绝、scene 字段边界与本地动作 allowlist。它们不证明真实 RT、真实 WinCraft WebSocket 或原生窗口行为。

## 待真实 host 验收

- 新 host 宣告 position_control 后，provider 能创建外心风格的无标题栏窗口并且从普通内容区拖动。
- provider geometry 保持尺寸控制，拖动只更新位置；紧凑/展开后恢复各自尺寸且不写回 ExoMind。
- 活动时间块暂停/继续由 ExoMind 原程序改变后，GET 投影诚实显示 paused/running；本 provider 不执行暂停/继续/结束。
- RT 断开时显示 stale 状态且不把旧快照冒充实时。
- 新建 provider world、动态收起/展开、hide、manager restore 和 clean disconnect 都只影响 WinCraft。
- 视觉像素与 ExoMind 浮窗的差异应在真实 Windows 当前 release 中观察；浏览器预览和 fixture 测试不能作为原生验收。
