# 交给本地 Codex 的整合提示词

> 本文件记录 2026-10-25 原型交接时的起始状态与验收顺序。后续已完成的验证摘要以 `docs/engineering/VALIDATION.md` 为准；机器专属细节见本地 `evidence/local/`（若存在）。不要把下方初始 `NOT_RUN` 状态当作当前结果。

请在这份 WinCraft 0.1.0-alpha.1 原型的解压目录工作。任务是**检验、修订、编译并跑通已有 Rust/Tauri 实现**，不是重新写一份计划，也不是换栈从零重做。

先读 `AGENTS.md` → `CODEX_HANDOFF.md` → `docs/product/DECISIONS.md` → `docs/engineering/VALIDATION.md`；再查看核心、服务、原生适配、共享渲染器和 Python 提供者。将已经明确的用户决定当作约束，不重新问是否使用 Rust、是否允许 Electron、是否窗口级独占、是否需要声明式组件。

核心产品定义：世界就是原生窗口；宿主仅常驻托盘；调用者是自动化程序，兼容 Agent，不提交 HTML/JS。组件支持连接期间的增删替换移动，不只是初始化模板。业务真相属于提供者，宿主只维护可重建的 UI/会话状态。窗口级独占写租约与多个快照读者先行，组件级借用后置。发现不授予操作权。无永久窗口绑定。管理器也是内部提供者，复用通用 renderer。用户可在本机明确撤销并接管窗口，旧写者不能偷偷夺回。远端通过安全隧道，不得为方便调试直接开放未加密公网监听。

原型的事实状态：TypeScript 严格构建、Node 单测、离线 schema/配置一致性与浏览器 DOM 检查在制作环境通过；Rust/Cargo 和 Windows 原生环境不可用，所以 Rust 编译、Rust 测试、真实 WebSocket、Tauri、托盘、点击穿透、多屏、release 与真实外心 RT 都尚未验收。`evidence/assistant-run/` 不是桌面成功证据。源码有 22 个 Rust 测试定义，不能计作已通过。

按依赖顺序推进：
1. 核对文件/来源，运行前端与契约检查；实际解析依赖并生成 lockfile。
2. `cargo fmt`、core/server 的 `cargo check/test/clippy`，先修语法、类型、借用和协议缺陷；保留错误及修复记录。
3. 编译运行**真实** headless Rust 宿主，运行 `examples/python/lease_probe.py`，补测租约过期、断线、重连、撤销栅栏与慢消费者，不能换成 Python mock。
4. Windows 上构建 Tauri；启动后应只有托盘。打开内部管理器，用 Python `focus_demo.py` 驱动真实原生世界，完成动态结构变化和动作回执。
5. 按 `docs/engineering/ACCEPTANCE.md` 执行人类拖动/提供者固定、穿透后救援、隐藏恢复、两个写者冲突、读者权限、不同 DPI/显示器、窗口关闭与宿主存活。
6. `npm run desktop:build` 后独立运行 release 可执行文件，再执行核心演示与故障测试；不能只验证 `tauri dev`。
7. 只有实际知道用户的 RT 地址与档案 ID，才运行默认只读的 `exomind_readonly.py`。不猜端口，不猜用户档案，不调用暂停/结束等写 API；连接信息缺失时标记这项 BLOCKED，继续其他测试。

优先保持既有设计不变量，最小修复 Tauri 2 API/ACL、Windows 行为和协议边界；不得用去掉鉴权/版本检查/lease epoch、注入任意代码、硬编码独立管理器页面等方式让演示变绿。遇到原型中的真实设计缺陷，提出最小修订、补回归并记录，而不是盲从已有实现。

在 `evidence/local/` 记录实际命令、环境版本、退出码与脱敏截图；更新验证矩阵，区分 PASS/FAIL/BLOCKED/NOT_RUN。不要覆盖 `evidence/assistant-run/` 原始记录，不要把令牌、runtime 描述文件、用户笔记或真实业务内容写入提交。输出可复现运行入口、构建产物实际路径、修复清单、仍未知的问题和下一阶段建议。

初始授权范围为本地工作目录内实现、依赖安装、测试、构建和临时测试窗口；不修改外心既有安装或业务数据，不擅自改许可证、注册名字或创建远程仓库。提交/推送需当前用户明确追加授权；获得授权后也只操作已存在且确认过的仓库与 remote。遵从当前宿主实际权限和用户追加授权。不要因尚有非阻断细节而停下来重复询问，先完成安全且可逆的验证。
