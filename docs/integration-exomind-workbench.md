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
| 数据源 | 当前 profile 的活动时间块、主窗口 profile 同步 | 仅显式 profile 的 active-timeblock GET |
| running full | FocusTimerWidget 单卡，源码 fallback 390×192；ResizeObserver 后以可见卡片 rect 为准 | 状态、任务名、计时、预计结束、只读提示；初始窗口采用源码 fallback 390×192 |
| running mini | 本地 React 状态切换 mini；源码 fallback 248×120，mini 可见卡片 CSS 宽 224 px；运行时以可见卡片 rect 为准 | provider 在本地切 scene 并 patch WinCraft size 到 248×120；展开恢复 390×192。这里有意复用 ExoMind fallback，实际 ExoMind 可能按 DOM 测量得到不同值 |
| 拖动 | data-tauri-drag-region 内容抓手；窗口不可手动 resize | 请求隐藏标题栏、背景可拖动、provider 尺寸、人类位置；依赖 position_control 能力 |
| 隐藏/恢复 | sessionHidden + ExoMind 主窗口服务 | WinCraft 本地 window.configure visible=false，由 WinCraft 管理器恢复 |
| 外心操作 | 外心 UI 暂停/继续/结束会写时间块 | 不接这些动作，提示用户回外心原程序操作 |
| 外观 | 卡片 CSS 使用固定 RGBA；未发现 Now Workbench 专属 opacity preference | 受限 theme_tokens + WinCraft surface opacity 0.8；不传 CSS |
| 虚拟桌面 | 当前 overlay source 未发现“所有桌面显示” API | 不请求跨虚拟桌面能力 |

**宿主能力前置条件：**该原型请求 geometry_control=provider + position_control=human，以锁定尺寸同时允许人类移动；这与只有单一 geometry_control 的旧宿主不兼容。provider 在创建世界前检查 window_property:position_control，旧 host 缺少此能力时会失败关闭，不降级成固定位置或可手动 resize 的错误体验。

当前 ExoMind now_workbench_overlay_restore_internal() 每次都回到默认右下位置，而拖动位置会另行持久化；reopenFromMainWindow() 调用 restore，因此“拖动→临时隐藏→从主程序重开仍保留位置”值得作为 ExoMind 自身回归用例。此原型不调用 ExoMind restore/position 写接口。

## 配置与运行

先从 exomind-monitor 的 get-config.js 取得当前 RT base 和 profile；不要猜端口、profile 或认证头。WinCraft runtime 必须来自本次 host manager/启动输出中的实际路径，不读取或打印 descriptor 内容。

示例（PowerShell）：

    $env:EXOMIND_RT_BASE = (& node 'C:\Users\<user>\.claude\skills\exomind-monitor\scripts\get-config.js' --rt-base 2>$null).Trim()
    $env:EXOMIND_PROFILE_ID = (& node 'C:\Users\<user>\.claude\skills\exomind-monitor\scripts\get-config.js' --profile 2>$null).Trim()
    $env:WINCRAFT_RUNTIME = '<本次 WinCraft manager 显示的实际 runtime descriptor 路径>'
    python examples/python/exomind_workbench.py

若 RT 需要鉴权，可按实际部署设置 EXOMIND_HEADERS_JSON。不要将令牌放入命令行、日志、截图或证据文件。远程 RT 必须使用 HTTPS 或 SSH tunnel；代码拒绝对非回环明文 HTTP 发送凭据。

provider 轮询 GET 的默认间隔为 1 秒，响应上限 128 KiB。HTTP 404 显示为“无活动时间块或端点需要核对”，不据此声称 RT 健康或档案为空。读取失败时，保留最后一次成功显示并标记来源读取失败；首读失败则显示无数据状态，不造出活动块。

按 Ctrl+C 停止 provider 时，它只尝试销毁自己创建的 WinCraft 投影世界；不会向 ExoMind 发送任何写请求。若 world.destroy 结果不确定，应在 WinCraft 管理器中核对这个原型世界，不要盲目重试。

## 本地测试

    python -m unittest discover -s tests -p 'test_exomind_workbench.py' -v

这些用例只使用 fixture，覆盖 running/paused 倒计时投影、空/404 歧义、active 路由 GET 方法、profile 显式绑定、远程明文 HTTP 拒绝、scene 字段边界与本地动作 allowlist。它们不证明真实 RT、真实 WinCraft WebSocket 或原生窗口行为。

## 待真实 host 验收

- 新 host 宣告 position_control 后，provider 能创建外心风格的无标题栏窗口并且从普通内容区拖动。
- provider geometry 保持尺寸控制，拖动只更新位置；紧凑/展开后恢复各自尺寸且不写回 ExoMind。
- 活动时间块暂停/继续由 ExoMind 原程序改变后，GET 投影诚实显示 paused/running；本 provider 不执行暂停/继续/结束。
- RT 断开时显示 stale 状态且不把旧快照冒充实时。
- 新建 provider world、动态收起/展开、hide、manager restore 和 clean disconnect 都只影响 WinCraft。
- 视觉像素与 ExoMind 浮窗的差异应在真实 Windows 当前 release 中观察；浏览器预览和 fixture 测试不能作为原生验收。
