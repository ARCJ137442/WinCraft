# 渐进路线

Windows 原生能力的细化计划（事件订阅、语义位置、Shell、主题、语音、捕获策略、窗口组合与提供者学习路径）见 [Windows 窗口运行时路线图](windows-roadmap.md)。它记录的是候选规划，不代表已经实现。

下一世代的需求、任务、验收和依赖已单独整理在[2026-10-26 平台演进交接包](strategy/2026-10-26/START_HERE.md)。当前先重定基线并推进协议能力门与 Popup 临时世界闭环；该包中标记为草案的契约仍需逐项落地和验证。

2026-10-30 对 B06 状态重新对齐：B06-01 配置包格式/导出与 B06-02 纯规划器在其 L1-L2 范围为 VERIFIED；B06-03 本机 `.wcp` 预览/提交/回退已进入 Rust Host 与通用管理器，但 A1-A3 仍 PARTIAL；B06-04 合成分享样例和文档已补齐，两个独立用户环境的重新授权验收仍 PARTIAL。当前 release build 已通过，管理器视觉交互因 Computer Use 状态读取失败而未验。详细状态与证据以 [`engineering/VALIDATION.md`](engineering/VALIDATION.md) 和策略任务账本为准。

## 阶段 0：本次原型源码

世界/窗口层级；单写租约与读快照；动态组件树；事件回执；托盘；内部管理器；外部 Python 提供者；TrafficMonitor 与 Obsidian Obsidian Workspace 本机只读投影。协议 0.3 的窗口文本默认可选属性已进入真实 lease probe；尚未完成的 Windows 手工验收见 [`engineering/VALIDATION.md`](engineering/VALIDATION.md)，机器专属证据位于默认忽略的 `evidence/local/nextgen-2026-10-26/`。

## 阶段 1：同一条真实链路跑通

Rust core/server 与 Tauri release 已构建并通过对应测试；最新真实 release lease probe 覆盖严格 0.3、窗口文本选择配置、认证、单写/读者、动态 patch、过期、重连 fencing 与慢消费者。TrafficMonitor x64 Lite 和 Obsidian Obsidian Workspace 的只读数据流均进入 Tauri 原生世界。剩余文本选择手势、点击穿透救援、人类/提供者几何、多屏/DPI、休眠恢复和 ACL 等边界继续按验证矩阵推进。ExoMind RT 由用户暂缓。

## 阶段 2：从一世界单写到多提供者组合

B07-01/02 的 `0.4-preview.1` 已实现窗口 authority、不相交子树租约、scope generation/local revision、原子子树结构 patch、父 authority revoke fencing、scope 删除通知与服务端过滤的 live scope snapshots；稳定 0.3 仍保持整窗独占。core invariants、Rust WebSocket integration 与真实 headless `scope_probe.py` 覆盖这三个 B07-02 验收点。B07-03 类型状态槽和 B07-04 多来源性质/按组件 owner 路由动作仍待推进。首个 host-owned `native_window_action` 已限制在 Obsidian/TrafficMonitor 与激活/恢复/最小化，且只在用户点击后执行；更广的应用注册、工作区锚定和窗口组合仍需逐项评审。

## 阶段 3：窗口行为成为可复用原语

先建立有类型的窗口事件订阅和受限响应；当前 `native_window_action` 仅由用户直接点击触发，事件驱动的应用聚焦请求仍未实现。随后探索工作区锚定、贴边、有限动作轨迹与按上下文显隐。行为在宿主本地执行，提供者表达意图，不通过网络每帧搬坐标。附着外部应用、光标跟随和临时透镜继续作为更高权限候选，须先验证目标生命周期、焦点限制、多屏/DPI 与救援路径。

## 阶段 4：桌面生态与熟练提供者路径

逐步探索可选的任务栏/Alt+Tab 曝光、TrafficMonitor 风格任务栏摘要、宿主托盘通知、AppBar、主题预设与受限 token 定制、区域输入、语音会话和捕获策略。高权能项目默认关闭；先有 capability、授权、原生回执和回滚，再进入 Agent 示例与课程。

## 阶段 5：蓝图、窗口组与生态

蓝图保存结构与布局，业务状态仍由提供者重建。探索多个独立世界的临时组合；设计组生命周期与原子操作时仍保留每个世界各自的租约。长期授权与安全通道；受签名/受控的组件扩展；普通用户配方；性能调度。不能把当前不做长期绑定误写成“产品永远不允许持久化”。

## 验证引导演进

若第二个独立提供者仍需修改宿主业务代码，先修正抽象；若多写者主要争的是窗口几何，先分 authority；若瓶颈是 UI 布局，不先换传输；若用户只需要临时工具，不先做常驻仪表盘生态。
