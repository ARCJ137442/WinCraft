# 制作环境实际验证记录

本地开发与 CI 的统一命令、CodeGraph 使用方式及证据边界见 [开发规范与工具链](DEVELOPMENT_TOOLCHAIN.md)。该命令的 CI 结果不替代本文件记录的真实宿主、release 和人工验收。

## 当前来源结论与历史记录阅读方式

截至 2026-10-30，Codex App 与 Claude Code 的 Agent Activity 数据路径是：本机进程只判在线/离线；获准的数据目录提供会话详情，离线时仍可读历史；没有权威逐会话状态就显示 `unknown`。不连接 Codex App，不启动 Claude CLI。下面带日期的早期记录仍保留当时的真实结果，但其中 MCP/connector bridge 与 `agents --json` 是被后续决定取代的历史方案；当前结果见文末最新 B08-02 记录和 `plan/status.json`。

本文件按时间追加，不回写早期观察。对同一验收项，较新的明确复核段落与生成的 `plan/acceptance.json`、`plan/status.json` 是当前状态；旧日期段落只保留发生当时的事实。

TeamSense 的 Codex 本机 rollout collector 与账号额度 collector 是不同来源：前者解析 rollout 的 `event_msg.token_count.rate_limits`，后者可选读取 auth 并调用实验性 Codex backend GET；`GET /v1/integrations/models` 则是另一条受 `data:read` 保护的 TeamSense 缓存 API。WinCraft B05-02 已改为只借鉴这些实现方法，不调用 TeamSense API、不需要 TeamSense token：Codex rollout 适配器只读有界 JSONL 尾部并投影 quota 字段；DeepSeek/MiniMax 使用显式 opt-in 的固定供应商 HTTPS GET 和本机环境 key；Codex live GET 仍作为单独实验性 opt-in 路径。对话正文、凭据、账户标识不会进入场景或日志。当前合成回归不读取真实 Codex 文件或凭据，也未发起外网请求；真实来源 freshness 和原生像素仍未验收。

## 2026-10-30 B02-02 主题与无障碍偏好验收

**Given** 提供者主题 token 与宿主可信标题栏，**When** 浏览器运行实际编译的 renderer 并模拟用户高对比、放大和减少动画偏好，**Then** 主题只影响 provider scene，用户字号优先，高对比与减少动画覆盖主题样式，无效主题回退。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| 首次 `scripts/browser_smoke.py` | FAIL（环境缺件） | 退出码 1；Playwright 管理的 Chromium 未安装。随后改用机器上已有 Chrome 执行同一项目 smoke；未下载或安装新浏览器。|
| `.venv\Scripts\python.exe scripts\browser_smoke.py`（`CHROMIUM_PATH` 指向已有 Chrome） | PASS（浏览器 renderer） | 退出码 0，28 个检查通过。包括 theme token 与可信 chrome 隔离、非法主题回退、用户缩放覆盖 provider scale、forced-colors 高对比覆盖、reduced-motion 将动画/transition 降为 0。结果存于忽略的 `evidence/local/nextgen-2026-10-30/b02-02-theme-accessibility-browser-smoke.json`。|
| B02-02-A1/A2/A3 | PASS（L1-L4 browser/contract） | 来源风格只影响 scene；宿主标题栏不被覆盖；高对比/用户放大/减少动画生效；非法主题不污染租约或业务数据。Windows 实际高对比设置、WebView2 UIA 与人工可访问性仍按 B02-04/B11-02 单独验收。|

## 2026-10-30 B02-03 教程动作分支回归

**Given** 新用户通过五课学习 Provider 的世界创建、数据更新、静态动作、主题和发现边界，**When** 合成事件进入 Provider 的动作处理器，**Then** 数据仍由 Provider 拥有、场景更新使用声明式协议，`world.list` 只用于汇总元数据，不加入或读取其他世界。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest tests.test_provider_tutorial -v` | PASS | 8 项 synthetic unit/schema 测试；覆盖五课合法组件、动态插入、选择/文本状态、主题应用/复位、计数发现、正常交互清理和有界运行时清理。发现动作只调用 `world.list`，不调用 `world.join`/`world.snapshot`，也不保留标题或世界 ID。|
| `npm run check:local` | PASS | 2026-10-31 恢复开发后的当前工作树：28 项 Node UI、149 项 Rust workspace、225 项 Python（1 项 symlink 环境能力跳过）；离线契约、Clippy 和 33 个 Provider Skill 引用检查通过，退出码 0。|
| 当前 release headless 教程 smoke | PASS（Provider 闭环） / PARTIAL（Host 退出） | `target/release/wincraft-headless.exe` 接受 `provider_tutorial.py --duration-seconds 5`；Provider 退出码 0 并确认只销毁自己的教学世界。测试后向隔离进程组发送 `CTRL_C_EVENT`，Host 在 5 秒内未退出；测试器仅终止该子进程（退出码 1），Host 未确认删除 descriptor，随后删除了隔离临时目录。因此不记 graceful Host shutdown PASS。摘要见忽略的 `evidence/local/nextgen-2026-10-31/tutorial-headless-smoke-20261031-resume/summary.json`。|
| B02-03-A1 新用户完整旅程 | PARTIAL | 有界真实协议 smoke 确认 Provider 可创建 synthetic 世界并销毁自己的测试世界；五课按钮/输入/主题/发现动作尚未通过原生点击连续验收。|

## 2026-10-30 B02-04 键盘与 IME renderer 覆盖

`evidence/local/browser-smoke.json` 的 28 项当前编译 renderer smoke 包括方向键选择、Tab 从选项进入备注、Ctrl+Enter 提交多行草稿、Escape 取消、IME composition 期间拒绝覆盖输入，以及迟到 ACK 不抢焦点。它只证明 Chromium 中的 DOM/事件行为。

| 验收 | 状态 | 边界 |
|---|---|---|
| B02-04-A1 键盘提交/取消与焦点 | PARTIAL | browser smoke 模拟键盘路径通过；实际 Tauri/WebView2 完整键盘旅程仍 NOT_RUN。|
| B02-04-A2 更新不打断 IME/草稿 | PARTIAL | synthetic composition 与 DOM draft 回归通过；实际中文 IME + WebView2 源更新仍 NOT_RUN。|
| B02-04-A3 DOM 不替代原生验收 | PASS | 验证矩阵分别标记 Chromium、UIA、IME、读屏和 native release，不用 browser PASS 推导 Windows 原生 PASS。|

## 2026-10-30 B03-02 Popup 状态机验收复核

**Given** 一次 Popup-Ask 临时问题，**When** 用户提交、取消、关闭，或 Host/Provider 断线，**Then** 每个路径产生单一确定结果或清楚的 unknown，并只清理本次世界。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest tests.test_popup_ask_provider -v` | PASS | 23 项测试覆盖 submit/cancel/escape/window-close/source-exit/host-exit、超过 10 秒等待、丢失 ACK、重复提交、busy 配额、原子位置保存与新 WindowSpec。|
| 重复 submit 与清理次序 | PASS（provider model） | 重复 submit 仅产生一个最终 action result 和一次本世界 destroy；取消 ACK 先于 destroy。测试使用 fake Client。|
| Popup 并发与可发现入口 | PARTIAL | Windows 跨进程互斥和 busy-before-client/create 通过测试；manager 逻辑列出 invite Popup world，但当前 release 可见性和不抢焦点未实测。|
| 位置恢复与键盘路径 | PARTIAL | 观察到的边界内位置/尺寸可持久化，新 WindowSpec 从保存偏好生成；Chromium 编译 renderer 验证方向键、Tab→备注、Ctrl+Enter 与 Escape。当前 release 原生几何复用、IME、UIA 和读屏仍未验收。|
| B03-02 acceptance | PARTIAL | A1/A2 由状态机与去重测试证明；A3/A4/A5 仍为 PARTIAL，完整 Tauri Popup 用户旅程待手动/原生验收。|

## 2026-10-31 B03-02 Popup 当前 release 超时清理 smoke

**Given** 一份仅含合成选项的 Popup-Ask 请求；**When** 已安装的 Popup-Ask skill 经 Provider 适配器在当前标准 Tauri Host 创建临时世界，并在 1 秒内没有收到人类输入；**Then** Provider 返回明确 timeout 错误并确认销毁自己的世界，不生成答案或重放提交。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Popup-Ask `--validate-only` 合成请求 | PASS | 已安装 `popup_ask.py` 校验 synthetic choice / descriptions / recommended 字段并注入 Other；无 GUI。请求文件仅留在 Git 忽略的本机证据目录。|
| 当前标准 Tauri release + `popup_ask_provider.py --timeout-seconds 1 --json --verbose` | PASS（L2 timeout/cleanup） | Provider 输出临时世界创建、timeout terminal JSON、`Popup-Ask temporary world cleanup confirmed.`；Provider 进程退出码 1 是预期的 timeout 结果，外层 smoke wrapper 捕获后返回 0。未提交答案；没有读取/保存用户内容。|
| `python -m unittest tests.test_popup_ask_provider -v` | PASS（23 tests） | 覆盖 busy gate、取消/关闭/断线/超时、重复提交、ACK 丢失、位置持久化与新 WindowSpec。|
| B03-02-A3/A4/A5 原生验收 | PARTIAL | 本 smoke 没观察焦点行为、位置复用、真实键盘/IME 或读屏。|

忽略的脱敏本机证据：`evidence/local/nextgen-2026-10-31/b03-02-popup-bounded-host-smoke.json`；合成请求文件同在忽略目录，没有 bearer token/runtime descriptor。

## 2026-10-31 B03-02 current Tauri Popup 并发槽位 smoke

**Given** 一个仅含合成选项的 Popup-Ask structured request；**when** 第一个 Provider 在当前标准 Tauri release 建立临时世界，另一个同用户会话的 Provider 并发启动；**then** 第二个调用返回 busy 错误“本次没有创建第二个窗口”，第一个请求结束后确认清理自己的世界。两个 Provider 均使用 `--no-remember-position`；本用例验证并发门控，不代替对焦点行为的屏幕观察。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| 已安装 Popup-Ask `--validate-only` | PASS | 当前合成请求有效；只做本地结构校验，不打开 Popup-Ask 自己的 Tk 窗口。|
| 当前 Tauri release + 两个独立 `popup_ask_provider.py` 进程 | PASS（busy gate） | 第一 Provider 打印临时世界已创建，bounded wait 结束并确认 `world.destroy`；退出码 1 对应 Popup 状态 `error`。第二 Provider 同用户 Mutex 返回 busy/error，退出码 1，消息明确说明未创建第二个窗口。busy-before-Client/create 的 focused regression 另外证明 busy 分支不实例化 Host Client。原始 response 文本未保留。|
| B03-02-A3 | PARTIAL | 真实 Tauri Host 上的并发槽位通过；界面是否抢焦点、管理器中如何发现现有 Popup 尚无原生截图/点击证据，Computer Use pipe 仍不可用。|
| Tauri Host、两个 Provider、descriptor 与位置记忆 | PASS | 首 Provider 世界清理成功；测试 Host 和两个 Provider 均退出；精确 runtime descriptor 已删除；`--no-remember-position` 避免读取/写入用户位置偏好。|

本机聚合证据为 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b03-02-popup-concurrent-20261031-142801/summary.json)；只保留合成场景、退出类别与清理状态，不保留响应文本、请求答案、PID 或 descriptor。

## 2026-10-30 B04-02 前台激活失败栅栏

**Given** 提供者请求经由用户点击触发的受限原生窗口动作，**When** `SetForegroundWindow` 报告拒绝且目标并未成为 foreground window，**Then** Host 返回明确错误，不写成功回执，也不把这次交互发布给 Provider。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo test -p wincraft-desktop rejected_foreground_request_is_not_reported_as_activation_success -- --nocapture` | PASS（Windows logic） | 当前 Windows 构建上验证 API success、API false 但 HWND 已为 foreground、API false 且仍非 foreground 三种分支；最后一种必须判定失败。|
| `cargo test -p wincraft-server native_window_action_failure_does_not_dispatch_or_ack_the_provider_event -- --nocapture` | PASS（Host integration unit） | native action 错误保持 `NATIVE_WINDOW_ACTION_FAILED`；不广播 Provider interaction、不创建 pending action、不产生 action ACK。|
| `cargo fmt --all -- --check` / `npm run check:local` | PASS | 退出码 0；28 项 UI、116 项 Rust workspace、174 项 Python（1 项环境能力跳过），Clippy 与 27 个 Provider Skill 引用检查通过。|
| `npm run desktop:build` | PASS | 退出码 0；`target/release/wincraft-desktop.exe`，13,279,232 bytes，SHA-256 `4EFE3DC6E5990E5A5BEE69116190C270CF7CD49527E2626207E60772F36ED806`。未运行新 release 的窗口点击验收。|
| B04-02-A3 Windows 前台拒绝 | PARTIAL | Win32 结果到 Host 的失败栅栏有定向回归；本轮没有强制 Windows 拒绝真实 Obsidian 激活。当前 release 标题动作的原生点击仍未通过 Computer Use/人工观察。|
| B04-02-A5 Host action / Provider ACK 顺序 | PARTIAL | Host native failure 测试不广播、不 ACK。当前通用 Obsidian Provider 尚未进行真实 release 点击验收。|

## 2026-10-30 B04-03 Manager 本机快捷键首个闭环

**Given** 用户在内部管理器输入 chord 并显式点击启用，**When** Tauri Rust adapter 注册 `manager.show` 全局快捷键，**Then** 默认启动不注册热键；只监听用户启用的组合，按下后重新呈现管理器，用户可一键停用。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Tauri Plugin Rust API | PASS（build） | 新增官方 `tauri-plugin-global-shortcut` 2.4.1，仅从 Rust 内部管理器 adapter 调用，不加入 JavaScript guest bindings/permissions。插件初始化时没有默认快捷键。|
| `cargo test -p wincraft-core shortcuts -- --nocapture` | PASS | 3 个 core 测试通过；chord 大小写/空白/修饰顺序规范化、等价 chord 冲突、owner revoke/unregister，以及 Windows/IME chord 失败关闭：Alt+Tab、Ctrl+Alt+Delete、Ctrl+Shift+Esc、Win+L/U、Ctrl+Space、Shift+Space、Ctrl+.、Win+Space、Win+/。IME 组合参考 [Microsoft Simplified Chinese IME](https://support.microsoft.com/en-us/windows/hardware/input-devices/microsoft-simplified-chinese-ime) 与 [East Asian input methods](https://support.microsoft.com/en-us/windows/hardware/input-devices/advanced-input-methods-for-east-asian-languages)。|
| `cargo test -p wincraft-server shortcut -- --nocapture` | PASS | 4 项测试覆盖本机显式启用/一键停用、默认不注册和断线撤销本 session intent。没有把 fake-host 结果当成真实 OS key event。|
| `cargo test -p wincraft-server failed_native_registration -- --nocapture` | PASS | 1 项测试确认本机注册失败时会回滚刚创建的 core intent；真实 OS 冲突仍未验。|
| `cargo test -p wincraft-server failed_native_unregistration -- --nocapture` | PASS | 1 项回归验证 native unregister 失败会保留 intent 并允许用户重试；实际 Windows OS unregister 仍未测。|
| `cargo check -p wincraft-desktop --all-targets` | PASS | 桌面 Tauri crate 与所有目标编译检查通过。|
| `npm run check:local` | PASS | 退出码 0：28 项 Node UI、141 项 Rust workspace、174 项 Python（1 项环境能力跳过），Clippy/离线契约和 27 个 Provider Skill 引用通过。|
| `CARGO_TARGET_DIR=target/stage-309af17 npm run desktop:build` | PASS | Exit 0；隔离产物 `target/stage-309af17/release/wincraft-desktop.exe`，13,559,808 bytes，SHA-256 `6840654D6DBEFB780B758618805B241AC96D22D57B8E7F4D49B102DFA3E58E10`；未覆盖仍运行的先前测试候选。|
| Release 源码提交 | PASS（对应源码） | `309af176714ffaf4d76601124a32e43ab2dfdd0b`；release 在该提交后构建。|
| Release 启动回归 | PARTIAL | 首次以 `--open-manager` 启动曾 exit 101：同步 Tauri setup 回调直接触发 `tokio::spawn`，panic 为 `there is no reactor running`。修复为从 `tauri::async_runtime::spawn` 调度 ManagerProvider；4bc3e81 候选在 5 秒观察后仍响应，管理器窗口和可访问性树可读。Clippy 修复后的 309af17 隔离 EXE 已构建但未另开第二个托盘宿主；须先退出当前旧候选再由用户/自动化验收。失败运行生成的 stale descriptor 已在不读取内容的情况下删除。|
| Release 管理器原生交互 | PARTIAL | Computer Use 截取到当前 release 管理器窗口/可访问性树；用户在快捷键输入框聚焦操作时按物理 Escape 停止了 Computer Use。没有输入或启用热键；字段焦点结果不确定，托盘交互、真实 OS key delivery、冲突和撤销均未验收。截图未保存为证据，因为画面包含本机 runtime 路径。|
| 快捷键 acceptance | PARTIAL | Manager 仅在本机 enable click 后注册 `manager.show`，并提供 disable；A1/A2/A3 的系统冲突、OS unregister 与 IME/输入焦点仍需真实 Tauri/Windows 验收。Provider 专属热键尚未开放。|
| GitHub Actions `41022563172` | FAIL（已修复） | Windows Clippy 1.99 报 `collapsible_match`；把 `ExitRequested` 条件并入 match guard，保留显式退出/最后世界关闭的原语义。修复见提交 `309af17`。|
| GitHub Actions `41024348330` | PASS | Windows `npm run check:local` 验证 `309af17`，所有步骤通过，耗时 12m22s；CI 不替代原生 GUI 验收。|

## 2026-10-28 开发工具链核验

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `npm ci` | PASS | 用已提交的 `package-lock.json` 干净安装成功；未改动依赖清单。|
| `npm run check:local` | PASS | 新增的统一入口退出码 0；覆盖 UI/离线契约、Rust workspace fmt/check/test/Clippy、Python provider 单测与 Skill 引用校验。28 项 UI 测试、78 项 Python 测试、19 个 Skill 引用检查通过。|
| Rust workspace 子检查 | PASS | `cargo fmt --all -- --check`、`cargo check --workspace --all-targets`、89 项 workspace 测试与 `cargo clippy --workspace --all-targets -- -D warnings` 均由统一入口执行并通过。|
| CI workflow / `package.json` 语法 | PASS | Windows 验证 workflow 可解析；脚本清单 JSON 可解析。|
| GitHub Actions Windows CI | PASS | B07-02 源码提交 run `40726526250`（commit `27b8677`）完整通过，`npm run check:local` 成功，耗时约 4m20s；checkout/setup-node/setup-python 均使用 Node 24 action releases。|
| CodeGraph | PASS（本机索引） | CLI 1.5.0；索引 69 个文件、1,628 个节点、5,196 条边，`status` 显示最新；索引数据库由 `.gitignore` 排除。它只用于导航，不代表代码验证。|

这次只验证工具链、文档与既有自动化测试；没有据此重新宣称桌面 release、托盘、原生窗口、外部业务数据或人工验收通过。逐机命令和环境记录位于默认忽略的 `evidence/local/nextgen-2026-10-28/`。

## 2026-10-28 GitHub Actions 失败调查

`dev` 上连续 9 次 Windows Actions 运行在 `npm run check:local` 中失败，范围从 `596a758` 到 `2bcb588`。setup、依赖安装和 Rust 工具链均成功；日志稳定指向两项 Windows 可复现问题：交接包校验对源 Markdown 原始字节做 SHA-256，导致 checkout 的 LF/CRLF 转换被误报为过期翻译；维护测试对 UTF-8 JSON 使用系统默认 CP1252 编码读取。

修复提交 `5e5f7e9` 将翻译源 hash 改为显式 UTF-8 文本 hash，并新增 LF/CRLF 等价回归；维护测试的 JSON 读写现在显式使用 UTF-8。该提交的 hosted run `40686753524` 通过。随后提交 `f63adfd` 将 Actions 更新为 checkout `v7.0.1`、setup-node/setup-python `v7.1.0`（均声明 Node 24）；run `40687743702` 再次完整通过，且不再出现 Node 20 deprecation 告警。

之后的文档同步提交也连续通过：`40689344687`（`f4122f4`）和 `40690440438`（`7610b80`）。前述九连败因此在 Windows 换行/编码回归修复后恢复为四次连续绿色；当时尚未推送的后续代码由单独的 hosted run 验证。

B07-01 代码提交 `be7a50c` 的 Windows hosted run `40707844155` 随后完整通过，耗时 6m16s。它覆盖了本机 gate 捕获并修复的 Clippy 回归、scope 协议实现和所有现有自动检查。

## 2026-10-28 B07-01 scope preview 与本机 CI 回归

| 检查 | 状态 | 实际结果 |
|---|---|---|
| 首轮 `npm run check:local` | FAIL，已修复 | UI、合同、Rust fmt/check/test 与 95 项 Rust 测试通过；Clippy 报告 scope 只读谓词可简化，以及 `join_scope` 参数过多。不是 hosted Actions 失败。|
| `cargo clippy --workspace --all-targets -- -D warnings` | PASS | 将谓词按 Clippy 建议归一；把 scope join 字段组合成强类型 `ScopeJoinRequest`，供 JSON 边界和 core 共用。|
| 最终 `npm run check:local` | PASS | 退出码 0：28 项 UI 测试、离线合同、Rust fmt/check、95 项 workspace Rust 测试、Clippy `-D warnings`、82 项 Python 测试和 19 个 Provider Skill 引用检查。|
| 真实 Rust headless `scope_probe.py` | PASS | 真实 WebSocket 对两个不相交子树分别写入，revision 独立递增至 4；读者只收到自身 subtree/namespace；稳定 0.3 整窗 writer 被拒绝；探针销毁自身世界并由 `world.list` 确认不存在。退出码 0。|
| Headless 停止与临时 descriptor 清理 | PASS（清理核实） | PTY 中 Ctrl+C 会把会话退出码报告为 1；随后核实 headless 进程数为 0、此次专用临时 runtime descriptor 不存在。未读取或保存 descriptor 内容。|
| B07-01 hosted Actions | PASS | run `40707844155` 对提交 `be7a50c` 执行完整 Windows `npm run check:local`，退出码 0，耗时 6m16s。|

本机命令、退出码、工具版本及脱敏探针结论保存在默认忽略的 `evidence/local/nextgen-2026-10-28/b07-01-ci-validation-20261028.json`。`0.4-preview.1` 是显式 opt-in 的 scope 实验协议，不改变稳定 0.3；B07-01 已达到其 L1-L2 范围的三项验收，但不代表原生 UI 或后续结构/动作路由已通过。

## 2026-10-29 B07-02 结构事务、父撤销与过滤快照

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Core ownership invariants | PASS | `cargo test -p wincraft-core --no-fail-fast`：8 个 core 单测、56 项 invariants 全通过。覆盖 scope 内原子结构变更、跨 scope 批量失败、根布局读取限制、父 release/disconnect/expiry fencing。|
| Rust WebSocket scope integration | PASS | `cargo test -p wincraft-server preview_websocket_scopes_allow_disjoint_writers_and_filter_readers --no-fail-fast`：真实服务连接通过；读者收到过滤后的实时 `scope.snapshot`，root 删除通知 `scope.revoked`，旧子 lease 被拒绝。|
| Python SDK / preview contracts | PASS | capability fail-closed、SDK scope cache/revoke 与 preview Schema 单测通过；结构操作和 root authority patch 均要求 Host 明确宣告能力。|
| 真实 Rust headless provider probe | PASS | `scope_probe.py` 退出码 0：两个子树独立更新、scope 内 insert/move、过滤 live snapshot、父删除撤销通知、旧 lease 拒绝、稳定 0.3 writer 拒绝；临时世界由探针销毁。|
| 本机完整 `npm run check:local` | PASS | 退出码 0：28 项 UI 测试、101 项 Rust 测试、86 项 Python 测试、离线合同与 19 个 Provider Skill 引用检查通过；包含 workspace fmt/check/test/Clippy `-D warnings`。|
| 独立 Tauri release 构建 | PASS | 已从提交 `27b8677` 执行 `npm run desktop:build`，退出码 0；实际 EXE 为 `target/release/wincraft-desktop.exe`，12,060,160 bytes，SHA-256 `572507C80123CB0236E4024BCA2AD51B97E7FD034C1963591287BBD2BE56DB98`，文件版本 `0.1.0-alpha.1`。|
| 真实 Tauri release 协议 | PASS | 对本次 release 的真实 host 运行 `lease_probe.py`，40 项通过；`scope_probe.py` 也通过 scope 结构事务、过滤 live snapshots、父删除与旧 lease fencing。两条命令退出码均为 0。|
| Tauri 管理器启动 | PASS（显式启动参数） | `wincraft-desktop.exe --open-manager` 启动后，Computer Use 窗口树显示“窗构 · 世界管理器”及管理器内容。此项不证明默认 tray-only 启动或托盘点击路径。|
| Tauri descriptor / 正常退出 | PARTIAL | 最终核对时进程已不存在；该运行创建的 AppLocalData descriptor 留存，按进程启动时间确认后删除，内容未读取。托盘菜单正常退出路径仍 `NOT_RUN`。|
| B07-02 hosted Actions | PASS | Windows run `40726526250` 对提交 `27b8677` 完整执行 `npm run check:local`，退出码 0。|

父 authority 的显式释放、断线、过期与本地 rescue 会推进子 generation/epoch 并轮换 scope grant；已加入读者保留只读资格并收到 stale scope 投影。删除布局父节点则移除对应 scope 与 data namespace，向既有成员发送 `scope.revoked`。稳定协议 0.3 行为未改变；组件动作路由、跨 scope move 与 CAS 状态槽仍未实现。

逐命令版本、退出码、probe 清理检查和脱敏结果保存在默认忽略的 `evidence/local/nextgen-2026-10-29/b07-02-validation.json`。原生托盘/像素验收仍按下方矩阵区分人工门，不由 headless probe 或 release compile 代替。

日期：2026-10-25。对应交接版本：0.1.0-alpha.1。这是原型制作环境记录，不是本地 Codex 的最终验收报告。

## 本机 Windows 验证摘要（2026-10-26）

以下结果来自当前 WinCraft 工作目录中的实际执行；原始制作环境记录保留在本文件下文，不再代表当前状态。

| 范围 | 状态 | 已证明的范围 |
|---|---|---|
| UI/离线契约 | PASS | `npm run check`：24 项 Node 测试、10 项离线契约/locale 检查；Chromium smoke 27 项编译 renderer DOM 检查，覆盖标题栏单击折叠/拖动阈值、健康状态与空徽标隐藏、状态播报、Tab 停靠与异步回执焦点；含 theme token/可信 chrome、字体缩放、forced-colors 与 reduced-motion 模拟；非原生验收 |
| Host UI 国际化 | PASS（B02 UIA） | Rust 管理器和 TypeScript chrome 共读 `zh-CN`/`en-US` catalog；fallback/key/placeholder 与 provider 文本测试通过。先前 B02 单实例测试进程的 UIA 树显示管理器动作；实际切到英文观察标题/按钮变化并恢复中文。最终版同含此 UI 代码，但未成功取得最终版 UIA 树。|
| Python provider/Agent skill | PASS | 最新 44 项 Python 单测、Provider Skill 自检 19 条唯一仓库引用；provider 的 live smoke 结果按脱敏记录保留，不在公开文档写入用户来源标识或业务投影内容 |
| Rust workspace | PASS | `cargo fmt --check`、workspace release 58 项测试、workspace Clippy `-D warnings`；含撤销幂等、跨 session lease fencing、world.list 可见性、theme contrast、scene atomicity 与全局临时窗口可见性状态 |
| Tauri release | PASS（已启动） | 先前独立 Tauri release 启动了世界管理器，`lease_probe.py` 对真实 Tauri 宿主 28 项通过。托盘退出与原生输入仍需单独验收 |
| 最终宿主 descriptor ACL | NOT_RUN | 通过 `client.py` 在内存中读取当前 descriptor 以连接，未输出或保存其内容；当前 descriptor ACL 未检查。此前 locale-enabled build 的 ACL 证据不能外推 |
| 真实协议 | PASS | `lease_probe.py` 分别对独立 headless Rust host 和当前 Tauri 启动的真实 Rust host 各完成 28 项；当前 Tauri host 额外报告 `native_windows=true`，窗口修订等待 native adapter 应用。未覆盖实际点击穿透救援、像素布局、托盘退出 |
| B01-02 撤销生命周期 | PASS | Rust core release 回归覆盖重复断线/离开幂等、其他 session/world 不受影响、pending action 撤销和旧 lease fencing；transport shutdown 测试确认活跃 WebSocket 断开、session/lease 清理、listener/housekeeping 停止及 descriptor 删除 |
| B01-03 授权 inventory / 世界发现 | VERIFIED（L1-L2，0.4 preview） | 0.3 `world.list` 保持 world-only 语义；0.4 preview 的 `provider.inventory.register/list` 处理已认证连接显式注册的来源元数据并返回 `endpoint_id`。注册的 capabilities 只是声明，Host 始终清空 grants；多 Host 汇总必须由调用者逐个选择和鉴权 endpoint。|
| B01-04 公共 SDK 与诊断 | PASS（L1-L2） | Schema/SDK/shared fixtures 与真实 Rust headless 一致；renderer 保留节点身份和草稿；Popup action-ack 断线时的合成敏感正文 sentinel 不回显 |
| 教程 provider | PASS（启动/清理），原生交互 PARTIAL | `provider_tutorial.py` 在真实 headless 与先前 B02 Tauri host 创建 ordinary invited world 并接受首个 scene；UIA 树显示五课首页。Ctrl+C 清理确认，随后 `world.list` 匹配数为 0；动态课/主题/隐藏恢复的 UIA 输入未完成 |
| TrafficMonitor | PASS（此前本机 smoke） | 临时 x64 provider 与本地桥接曾报告来源在线且采样更新；本公开记录不含本机进程标识或遥测数据 |
| Obsidian Workspace 示例 | NOT_RUN | 通用插件、Provider 和人工启动入口已纳入源码；真实 Obsidian 插件加载、实例快照更新与原生窗口激活尚未验收。|
| Python focus demo | PASS（连接），动作回执 NOT_RUN | `focus_demo.py` 已连到当前 Rust host 并创建合成世界；窗口可用于人工测试动态组件替换与动作回执。没有代替用户点击按钮 |
| GitHub | PASS | `ARCJ137442/WinCraft`、默认分支 `dev`、`origin` 已建立；按用户最新决定仓库公开。源码首个提交 `c70ba44`、路线图 `3661dce`、文本选择功能 `73c3e20` 均已在远端 |
| 用户观察 | PASS（此前版本） | 用户确认托盘图标/菜单可用、悬浮窗可见且可拖动；最新替换后的 release 尚未要求用户重复做这些手工观察 |
| 原生人工门 | PARTIAL | UIA 树可读出管理器/教程窗口 role、名称、状态与动作；manager 中英切换已实际操作并恢复。Computer Use 对 tutorial 窗口两次恢复后仍报 `failed to activate captured window`；隐藏/找回、Popup Tab→备注→Ctrl+Enter/Escape、IME/屏幕阅读器、多 DPI、休眠恢复和穿透救援仍未完成人工验收 |
| ExoMind | PARTIAL（只读 smoke） | 新工作台 provider 完成一次用户授权的真实 `GET /timeblocks/active` 与内存投影，未调用 ExoMind 写 API；13 项合成 fixture 覆盖 full/compact/mini、idle、404 与 stale。真实返回值不留在公开记录；原生像素、模式点击与稳态尺寸仍 `NOT_RUN`。|

Lifecycle release 与临时 provider 的进程清理曾在本机完成。一个过期 runtime descriptor 的删除尝试被本机策略拒绝；该文件内容未读取。逐机进程、路径和 descriptor 清理证据仅保存在本地忽略目录。

## 已实际执行

| 项目 | 结果 | 证据/范围 |
|---|---|---|
| TypeScript 5.8.3 严格编译 | PASS | 实际源码编译为 ES2022，strict/noUncheckedIndexedAccess/noEmitOnError |
| Node.js v22.16.0 单元测试 | PASS，12项 | `evidence/assistant-run/ui-tests.log`，数据绑定/格式/属性安全等 |
| 离线契约检查 | PASS，8类检查 | `contracts.json`：JSON/TOML/Python语法、schema正反例、方法源码存在、无动态代码、路径依赖 |
| Chromium实际编译模块的DOM检查 | PASS，9项 | `browser-smoke.json`，同一 renderer、模拟provider，**非Tauri、非真实WS** |
| 许可原文 | PASS | 根LICENSE Git blob hash与ExoMind `6e73a892c873e6244dcf669d38b5b56140b90f25`一致 |
| 文件/文档完整性 | 见 `artifact-audit.json` | 相对文档路径与打包文件检查，非语义正确性证明 |

原始日志保存在 [evidence/assistant-run](../../evidence/assistant-run/)。浏览器截图也在该目录；它们只是实际前端代码的浏览器预览，不是Windows截图。

## 浏览器验证的精确边界

制作环境的 Chromium 策略拦截了 localhost 顶层导航。没有关闭或修改浏览器安全策略；检查脚本通过 `page.set_content` 放入宿主页面，并用内存 blob 加载**同一份实际编译后的 TypeScript 模块**，仅改写模块 import URL。Node 本地静态服务另经 HTTP 请求检查。环境使用 `WINCRAFT_OFFLINE_BROWSER=1` 选择这一明确标记的路径。

已验证：演示有标签、无关刷新不丢草稿与DOM身份、动态替换组件、输入回到模拟提供者、文字不作为HTML解析、过期世界禁用按钮、中文组合输入不中断、管理器fixture复用renderer、无浏览器运行时错误。

没有验证：Tauri IPC、CSP在真实Tauri环境的效果、Rust业务状态机、实际WS回执、托盘、置顶、穿透、显示器/DPI、native窗口可达性、真实外心或远程设备。

## 未执行／不能宣称完成

| 项目 | 状态 | 原因 |
|---|---|---|
| cargo fmt/check/test/clippy | NOT_RUN | 制作环境没有cargo/rustc；已写22个Rust测试，但不能计作通过 |
| Axum真实headless + lease_probe | NOT_RUN | Rust程序未编译，未用替代后端冒充 |
| Tauri 2开发构建与运行 | NOT_RUN | 无Windows桌面与Rust工具链 |
| 独立Windows release | NOT_RUN | 无可执行构建产物 |
| 实际网络握手/远端SSH | NOT_RUN | 仅协议/客户端源码，未连实际服务 |
| Python模拟provider业务循环 | NOT_RUN（真实连接） | AST检查不是运行链路 |
| 真实ExoMind RT桥接 | NOT_RUN | 本轮没有用户实际运行端口/档案/现场权限信息 |
| Windows ACL、多屏、IME原生路径 | NOT_RUN | 浏览器DOM验证不替代原生测试 |
| 性能、耗电、稳定性 | NOT_RUN | 没有可靠基准，不填造数字 |
| CI工作流 | NOT_RUN | 仅交付workflow文件，没有创建或运行远程Actions |

## 复现已执行部分

本地先 `npm install`；无需使用制作环境的编译器路径。制作环境因无网络依赖安装，使用预装 TypeScript 5.8.3，由 `TSC_JS` 指向本机既有编译器，**没有复制其node_modules或字体**到交接包。

```powershell
npm run test:ui
python -m pip install -r requirements-dev.txt
python scripts/check_contracts.py
python scripts/browser_smoke.py
```

浏览器脚本默认使用本地 dev URL；本机缺 Chromium 时可运行 Playwright 的浏览器安装命令，或用 `CHROMIUM_PATH` 指向本机 Chromium。依赖锁文件应由本机真实解析生成。本轮容器网络/DNS不可用，没有伪造下载成功。

## 后续记录方式

本地Codex将自己的结果写入 `evidence/local/`，新建本地验证摘要。保留本文件作为初始事实基线。修复后的代码需要复跑对应检查，不能把制作阶段的截图延续成修改后仍通过的证据。

## 2026-10-26 下一世代基线与 Popup 切片

本节为当前仓库新一轮验证，不覆盖上面的原型基线。基线 HEAD 仍是 `6929056700b1ba6702288534579debc8a502c139`，交接包已整合到 `docs/strategy/2026-10-26/`。协议仍为 `0.3`；新能力是 capability-gated 的 `textarea`、单选/多选选项组、Escape 与 textarea Ctrl+Enter 事件。旧 host 未宣告能力时，Python client 会在创建世界前失败。

| 范围 | 状态 | 当前证据 |
|---|---|---|
| UI、Schema、Provider Python | PASS | `npm run check`：24 Node tests、10 项离线检查；Python 单测 44 项；Provider Skill 自检 19 条唯一引用 |
| Rust core/server/desktop | PASS | rustfmt；workspace check；release 58 项测试；workspace Clippy `-D warnings` |
| 编译 renderer DOM | PASS | Chromium 27 项离线检查，含多行草稿、选项组键盘、标题栏点击折叠与拖动阈值、健康状态徽标隐藏、主题 token/宿主 chrome 隔离、本机缩放、forced-colors/reduced-motion、状态语义和焦点不抢夺。Mock provider，不是 native 证明 |
| 独立 Tauri release | PASS（构建、启动） | 先前独立 release 在管理器模式启动，真实 Tauri host 协议探针通过；机器专属路径与进程号不放在公开记录 |
| Scene theme tokens | IMPLEMENTED_UNVERIFIED | `scene.theme` capability、Rust 对比度/范围验证、renderer 内容区作用域、forced-colors/reduced-motion 与本机 Ctrl 缩放已实现；DOM/headless probe 通过，Windows 原生偏好仍待验收 |
| Theme demo provider | PASS（unit） | `examples/python/theme_demo.py` 仅展示合成主题；能力门、默认/示例主题、低对比负例由 3 项单测覆盖，尚未在新 Tauri release 上运行 |
| Provider 五课教程 | IMPLEMENTED_UNVERIFIED | `examples/python/provider_tutorial.py` 含创建/隐藏找回、动态插入、交互回执、主题、发现/加入边界；44 项 Python 测试包含六项教程回归；headless 与先前 B02 Tauri host 均接受初始 scene，UIA 显示首页控件，provider 清理已验证；完整 Tauri 五课互动仍待用户验收 |
| Host UI 国际化 | PASS（B02 UIA） | 先前单实例 B02 manager 的 UIA 树确认控件/动作；切换英文后观察标题/按钮变化并恢复中文；最终版包含相同 i18n UI 代码，但 Computer Use 未再捕获最终版 UIA 树 |
| 当前 release 的真实 Rust host | PASS | 最新 headless Rust Host 与当前 lifecycle Tauri host 的 `lease_probe.py` 均 28 项通过；Tauri host 报告 `native_windows=true` 并应用被测窗口修订，不证明像素布局或人工穿透救援 |
| Popup-Ask 兼容接口 | PASS（局部） | 本地安装的 `popup_ask.py` validate-only、Other 注入与成功 JSON 序列化已连接；首次真实 Popup 成功结果使用合成请求，原始答复未保留 |
| Popup provider 终态/清理流 | PASS（unit） | 6 个 run-loop 测试覆盖取消 ACK/销毁次序、窗口关闭、超时、断线、ACK 未知、普通选项 ACK 不结束人类等待及清理失败；注入 fake Client，仅证明 Python 编排，不证明 Rust Host 或 Tauri 输入 |
| 新键盘流和中英切换的真实 Tauri 输入 | NOT_RUN | 窗口可被 Computer Use 截图和读取 accessibility tree，但 helper 无法激活目标窗口；未伪造键盘输入。需要人手验收 Tab→备注→Ctrl+Enter、Escape 与管理器语言切换 |
| 原生位置复用 | NOT_RUN | 提供者实现只保存本机原生位置/尺寸偏好，单元测试通过；同一设置下第二次 release 弹窗的位置仍需实机观察 |
| 多 Popup 并发与来源/Host 退出竞态 | NOT_RUN | 尚未验证 Popup 专用并发配额、抢焦点策略和所有故障组合 |

## B01-02 / B01-03 生命周期与发现（2026-10-26）

| 事项 | 状态 | 证据与边界 |
|---|---|---|
| B01-02 会话撤销幂等 | PASS | core release 回归：重复 disconnect/leave 不再次推进 epoch/sequence，writer A 撤销不会移除 reader B 或 B 的另一个 writer world；撤销时 pending action 进入 error。|
| B01-02 跨 session 句柄隔离 | PASS | 断开 A 后注册新 session，取得更高 epoch；用旧 lease 写入返回 `STALE_LEASE`，scene data 不变。|
| B01-03 `world.list` 可见性边界 | PASS（协议增量） | 仅返回当前 session 已加入的世界和非系统 `open_authenticated` 世界；未加入 invite 世界不暴露 ID/title/writer。operator 仍可供管理器列出全部世界。|
| B01-03 实例/权限/状态 | PASS（core + headless） | 两个同名开放 world 保持不同 ID；列表 metadata 不含 join_key/lease/scene/data；online/stale/vacant 与 FORBIDDEN join 可区分；真实 `lease_probe.py` 28 checks 通过。|
| B01-03 多来源 inventory | PASS（0.4 preview L2） | 真实 loopback WebSocket 测试注册/读取来源 inventory；相同 `id` 的实例由不同 `instance_id` 区分，Host 拒绝自授 grants并返回 endpoint ID，断连来源变为 offline，快照过期变为 degraded、TTL 到期后清理。0.3 `world.list` 未改变。|
| `cargo test -p wincraft-server -p wincraft-core --no-fail-fast` | PASS | Core 10 unit + 61 invariants、Server 26 tests 全部通过，退出码 0；含 authenticated loopback inventory register/list、endpoint identity、no-grant 与 invitation join refusal。|
| `python -m unittest discover -s tests -p test_client_capabilities.py -v` | PASS | Python 3.11.4；20 项通过，退出码 0；SDK 在 capability 未声明时 fail closed，且校验 inventory endpoint ID 匹配 hello host ID。|
| `python scripts/check_contracts.py` | PASS | Provider inventory 注册/输出 schema、正反 fixtures、preview manifest 和 handoff planner 检查通过，退出码 0。|
| `cargo test -p wincraft-server -p wincraft-core --no-fail-fast` | PASS | Core 10 unit + 61 invariants、server 26 tests 全部通过，退出码 0；含 authenticated loopback inventory registration/list、endpoint identity、no-grant 与 invitation join rejection。|
| `python -m unittest discover -s tests -p test_client_capabilities.py -v` | PASS | Python 3.11.4；20 项通过，退出码 0；SDK 对未宣告 capability fail-closed，并验证 inventory `endpoint_id` 匹配 hello `host_id`。|
| `python scripts/check_contracts.py` | PASS | Provider inventory 注册/输出 Schema、正反 fixture、preview manifest 与 handoff planner 检查通过，退出码 0。|
| 原生 manager language toggle | PASS（UIA tree） | 单实例 Tauri manager 从中文切换为英文并在 UIA 中观察到标题/动作文本更新，之后观察到中文已恢复。|
| 教程隐藏恢复/Popup键盘/IME/读屏 | NOT_RUN | Computer Use 对唯一教程窗口执行首次点击与一次重新激活仍失败；没有再尝试其它 UI 输入通道。manager、tutorial UIA 树的控件名已读取，截图回传错窗后丢弃且未保存。|

2026-10-29 B01-03 验收范围：inventory 是每个 Host endpoint 的内存 registry；多 Host 汇总由调用者对明确选择的 descriptor 分别鉴权后处理，Host 不自动扫描。能力声明不是授权，注册不接受 grants，列表不改变 world membership 或 lease。

此前的 manager/provider 进程已按所属项目范围清理。Computer Use 恢复失败后没有再发送键鼠输入。UIA/IME/屏幕阅读器和五课完整交互仍待人工验收。

## B02-03 / B02-04 本轮增量（2026-10-26）

| 事项 | 状态 | 证据与边界 |
|---|---|---|
| 五课 Agent provider 教程 | PARTIAL（历史 release 测试） | 2026-10-26 记录包含五课场景、动态插入、回执、主题、发现计数及隐藏恢复；后续记录仍将完整用户旅程列为待验，且未找到覆盖 A1 全部动作的专用运行证据，因此不把摘要直接升为 PASS。|
| 教程运行与清理 | PASS（历史 release 运行） | 先前一次 release 运行记录了五课窗口出现、提供者退出后管理器计数为 0；这证明该次运行的清理，不证明五课全流程用户验收。本轮新启动未观察到教程窗，清理状态另记为未确认。|
| 焦点与待处理动作 | PASS（DOM） | pending 动作期间用 `aria-disabled` 保留键盘焦点，按组件阻止重复提交；回执只在原控件仍持有焦点时恢复，不把焦点从用户后来选中的控件抢回；Chromium smoke 回归通过。|
| 连接状态可访问性语义 | PASS（DOM） | `#status` 标记 `role=status`、`aria-live=polite`、`aria-atomic=true`；主窗口移除无用途的额外 Tab 停靠，滚动组件区仍可键盘聚焦。|
| 本地统一门禁 `npm run check:local` | PASS | 当前工作树：28 项 Node UI、116 项 Rust workspace、174 项 Python（1 项环境能力跳过）；契约、Clippy 与 27 个 Provider Skill 引用检查通过，退出码 0。|
| Windows UIA/原生键盘/IME/读屏 | PARTIAL | 本轮通过当前 release 的 UIA 树验证教程五课、动态结构、回执、主题、窗口拖动及隐藏/管理器恢复；IME、真实键盘快捷键和读屏仍 NOT_RUN。|

shutdown 版在独立 Cargo target 中构建并以单实例运行。Computer Use 曾无法激活教程窗，未绕过该限制继续发送键鼠；人工 UIA/IME/读屏/五课验收仍待完成。

## 2026-10-30 B02-03-A1 教程交互复核

此前记录摘要称五课 release Tauri 流程已走完，后续记录又把完整用户交互列为待验；本机 `evidence/local/nextgen-2026-10-30/` 中也没有覆盖 A1 全部动作的旅程证据。当前 acceptance 状态定为 **PARTIAL**，等待可复核的完整用户流记录。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Release 宿主/描述文件选择 | PASS（只读准备） | 唯一 release 进程与其本机 runtime descriptor 通过 PID 匹配；不保存描述文件路径或内容。|
| 五课 Provider 启动 | PARTIAL | 以合成数据启动 `provider_tutorial.py` 后，进程在后续观察前已退出，Computer Use 未观察到教程窗口；该启动本身不能证明课程交互。|
| 2026-10-31 当前 release 有界启动/清理 | PASS（L2） | `python -u examples/python/provider_tutorial.py --duration-seconds 5 --title <synthetic QA title>` 退出码 0；收到启动行、时限到达和 `world.destroy` 清理确认。仅用合成课程数据，不代表课程交互通过。|
| 2026-10-31 当前 release 无界启动复试 | NOT_RUN | 启动尝试没有返回确认；进程随后被中断并退出。只读非 operator `world.list` 返回 0 个可见世界，但邀请世界对该会话不可见，不能证明这次早先尝试是否清理。此尝试不算通过。|
| 管理器窗口交互 | BLOCKED | 新枚举到唯一管理器后，Observed 的展开按钮 click 与一次重新枚举恢复均返回 `foreground window did not report a process id`；按 Computer Use 恢复规则停止后续输入。|
| 有界 smoke 世界清理 | PASS（L2） | Provider 收到其 `world.destroy` 成功响应并打印确认；只证明本次 5 秒测试世界已清理。|
| 早先中断尝试的世界清理 | NOT_RUN | 非 operator `world.list` 不能看见 invite-only/system 世界；该次创建结果未确认，管理器侧仍需核实。|
| 教程动作分支回归 | PASS（synthetic unit） | 新增定向测试覆盖选择/文本输入经 `data.replace`、主题应用/复位经 `scene.replace`、动态插入经 `scene.patch`；发现只调用 `world.list`，场景只收到计数/加入策略、不加入或读取目标世界。`python -m unittest tests.test_provider_tutorial -v` 7 项通过。|
| A1 新用户完整旅程 | PARTIAL | 建窗、改字、按钮、主题、课程发现未在本次连续完成；保留为人工验收/可用 UI 自动化路径待办。|

脱敏运行摘要见忽略的 `evidence/local/nextgen-2026-10-30/b02-03-tutorial-cua-recheck.json`、`evidence/local/nextgen-2026-10-31/b02-03-tutorial-current-host-attempt.json` 和 `evidence/local/nextgen-2026-10-31/b02-03-tutorial-bounded-release-smoke.json`；没有记录 runtime descriptor、token、真实会话或业务数据。

## B03-01 Popup 兼容适配（2026-10-26）

| 用例 | 状态 | 证据 |
|---|---|---|
| B03-01-A1 原正反输入与输出格式 | PASS | 直接调用本机已安装的 `popup_ask.py`：合成正例 `--validate-only` 退出码 0 并由原 skill 注入 Other；重复标签反例退出码 1；adapter 默认 stdout 与原 `render_payload_for_stdout` 一致，JSON 与原成功 payload 结构一致。未打开 Tk 窗口。|
| B03-01-A2 取消 reason 保持兼容 | PASS | provider 单测区分按钮/Escape/关闭原因；断线保留 unknown。|
| B03-01-A3 本地 ACK 不结束人类等待 | PASS | 新增 run-loop 回归：选项交互被 `action.result` 确认后，provider 继续消费后续取消事件；它不把单次普通动作回执当作整体问题答案。|
| B03-02 Popup 原生交互与位置复用 | NOT_RUN | 当前仍须单实例 Tauri UIA/键盘路径验收；Computer Use 无法激活教程窗口，尚未向 Popup 注入键盘。|

本轮证据摘要在被忽略的 `evidence/local/nextgen-2026-10-26/popup-b03-01-validation.json`。此验证使用合成请求，没有保留题目答案或真实用户文本。

完整命令、退出码、修复记录和脱敏运行报告位于被忽略的 `evidence/local/nextgen-2026-10-26/`。没有改许可证、远程分支或外心数据；当前未提交、未推送。原始 `evidence/assistant-run/` 未修改。

## 2026-10-26 Lifecycle release：真实 Tauri host 协议验证

- 先前 lifecycle release 使用 `--open-manager` 成功启动「窗构 · 世界管理器」；真实 Tauri host 上的 `lease_probe.py` 28 项通过。
- `lease_probe.py` 通过进程内读取当前运行时 descriptor 认证连接；不在公开文档记录 descriptor 内容、路径或业务数值。
- 同一宿主的短连接只输出 `native_windows=true`。探针通过 native adapter 修订状态检查了 provider 隐藏/恢复、透明度、标题栏/点击穿透设置；这验证原生适配状态已应用，不证明像素布局正确，也不证明真实鼠标穿透或救援操作。
- 旧 manager 与临时 provider 曾按项目范围清理；一个本机策略拒绝的过期 descriptor 删除操作没有读取文件内容。手动托盘退出、键盘/IME/读屏、多 DPI、多屏、教程完整交互与 Popup 键盘流仍待验收。
- TrafficMonitor 与 focus demo 的本机 provider smoke 曾观察到来源在线与窗口更新；通用 Obsidian Workspace 集成另列为 NOT_RUN。
- TrafficMonitor x64 bridge 曾以本机源码重编并在隔离 staging copy 中验证；具体本机路径与实时遥测值留在忽略的本地证据。
- 本次环境：Windows 11 Pro 10.0.22000 x64、Python 3.11.4、Node v22.23.4、npm 11.19.0、Cargo 1.93.0、rustc 1.93.0。脱敏结果位于被忽略的 `evidence/local/nextgen-2026-10-26/lifecycle-tauri-lease-probe.json`。

## 2026-10-27 原生窗口动作

| 范围 | 状态 | 实际结果与边界 |
|---|---|---|
| UI / schema / provider | PASS | `npm run check`：24 Node tests、10 项离线契约检查；Python 全套 58 tests；`scripts/check_contracts.py` PASS；Provider Skill 引用检查 19 项 PASS。Schema 与 Rust 接受 `obsidian`/`traffic_monitor` 及 `activate`/`maximize`/`restore`/`minimize` 枚举。|
| Renderer DOM | PASS（非原生） | Chromium offline DOM 28 项通过，包含可点击标题、title 外观、allowlisted SVG、状态图表、动态结构和健康状态徽标；Mock provider 不验证 Tauri/Win32。|
| Rust core/server/desktop | PASS | `cargo fmt --all -- --check`、`cargo check --workspace`、`cargo test --workspace`、`cargo clippy --workspace --all-targets -- -D warnings` 全部通过；workspace 测试 66 项。新增回归覆盖应用映像映射、大小写无关标题筛选、操作 allowlist、stale/revoked/disabled/context guards、headless capability 拒绝，以及 manager 列出 invite Popup world 不改变其 writer/epoch。|
| 独立 Tauri release | PASS（构建、启动） | 历史独立 release 默认托盘模式运行；机器专属产物路径与 runtime descriptor 未写入公开记录。|
| 当前源码 release | PASS（构建）／NOT_RUN（启动） | 当时从当前源码构建成功；机器专属产物路径仅保存在本地证据。|
| 当前 release 的真实 Tauri host | PASS（协议） | `lease_probe.py` 31 项通过；`native_windows=true` 时宣告 `external_window_actions`。完整协议探针仍使用合成数据，不证明人工鼠标路径。|
| 当前代码的真实 headless Rust host | PASS（协议） | `lease_probe.py` 31 项通过；`native_windows=false` 时不宣告并拒绝外部窗口动作。临时 headless 进程已退出；临时目录尚有一个 descriptor 文件，内容未读取，也未复制进仓库或证据。|
| TrafficMonitor provider | PASS（真实来源链路） | 新 x64 TrafficMonitor 副本仍运行；新 provider 连上本次 release，状态为空、age=0、generation/revision 持续增长并报告 1.8.6.0。日志没有记录指标读数。|
| Obsidian Workspace 数据链路 | NOT_RUN | 当前通用插件/Provider 代码还没有真实 Obsidian 插件与 release 宿主联合验收。|
| Popup-Ask 并发配额子项 | PASS（unit/cross-process/current Tauri busy smoke） | Windows 本机会话命名互斥体限制一个 Popup-Ask provider；同进程、独立子进程竞争和 busy-before-client/create 均有回归。当前 Tauri release 上第一个合成 Popup 世界创建并由 Provider 清理，第二个独立 Provider 返回 busy/no-second-window。server unit 还确认 manager scene 会列出 invite Popup world 且不改变其 writer/epoch；管理器可见性、实际焦点是否被抢仍 NOT_RUN，因此 B03-02-A3 整体保持 PARTIAL。|
| Popup provider 状态机与 headless wire | PASS（自动） | 22 项 Popup 专项测试覆盖成功 ACK 后单次销毁、重复 submit、取消/Escape/窗口关闭、超过 10 秒的整体等待、断线、ACK未知、busy 时错误退出与清理失败；Rust manager unit 确认 invite Popup world 出现在管理器 scene 且 writer/epoch 不变；真实 Rust headless host + 安装的 Popup-Ask skill 对合成请求验证 timeout/world.destroy 与并发 busy 拒绝，关闭后 descriptor count=0。首次 PowerShell 汇总器对空 stderr 调用 `.Contains` 而退出 1；后续 Python 结构化解析确认了所有结果字段，失败与复核均保存在本机证据。真实 Tauri Popup 的成功/取消、键盘/IME/读屏、管理器可见性及 native position reopen 仍 NOT_RUN。|
| 原生窗口动作人工点击 | NOT_RUN | 当前通用 Obsidian Workspace 标题声明受限的 `obsidian/activate`；真实 release 点击与 Windows 前台限制成功/失败路径仍待本机观察。|
| 托盘管理器打开与全局隐藏/显示 | NOT_RUN | 早期版本中用户报告“显示世界管理器”无响应；新 release 尚待用户重新检查托盘菜单、管理器聚焦和全局隐藏/恢复。|
| ExoMind | BLOCKED（用户暂缓） | 没有读取连接配置、猜测端口/profile 或调用 API。|

执行环境：Windows 11 Pro 10.0.22000 x64、Python 3.11.4、Node v22.23.4、npm 11.19.0、Cargo 1.93.0、rustc 1.93.0。脱敏命令结果保存在被忽略的 `evidence/local/nextgen-2026-10-27/native-window-actions.json`。真实窗口操作仍需人工验收；浏览器预览和 headless 探针不替代这一步。

交接包自身也在 2026-10-27 重生成任务视图：`validate_handoff.py` 为 43 篇文档、141 条相对链接、73 项需求、48 个任务、147 个验收项和 17 个 Schema 样例返回 PASS；包内 34 tests PASS。B04-02 仅进入 `IN_PROGRESS`，其中 native allowlist/headless gate 的 A4 为 PASS，Windows 前台拒绝路径 A3 和真实用户点击 A5 仍为 `NOT_RUN`。本地 `MANIFEST.sha256` 重建为 98 条，和原始 `SOURCE-MANIFEST.sha256` 相比保留两个既有本地新增项，未列入生成的 `__pycache__` 文件；哈希复核 0 mismatch。

## 2026-10-27 通用原生窗口动作扩展

在既有的跨应用动作 allowlist 中加入可逆的 `maximize` 操作；可用操作现在为 `activate`、`maximize`、`restore`、`minimize`。目标仍限宿主登记的 Obsidian/TrafficMonitor 应用和用户点击的有效按钮；没有扩展到任意进程、进程启动/关闭、脚本或原始 HWND。通用能力分层与后续候选见 `docs/windows-roadmap.md`。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo fmt --all` / `cargo fmt --all -- --check` | PASS | 修正一次新增断言的格式后，格式检查退出码 0。|
| `cargo test --workspace` | PASS | 66 tests passed（core 43、desktop 13、server 10）；包含动作 schema 解析与 allowlist 正反例。|
| `cargo check --workspace` / `cargo clippy --workspace --all-targets -- -D warnings` | PASS | 两项退出码 0；Windows Tauri adapter 成功编译。|
| `npm run check` | PASS | 24 Node tests 与 10 项离线契约检查通过，包含新 maximize scene fixture/schema。|
| `python skills/wincraft-provider/scripts/verify.py` | PASS | 19 项 Provider Skill 链接/引用检查通过。|
| `npm run desktop:build` | PASS（构建）／NOT_RUN（启动） | 使用独立 target 构建成功；机器专属产物路径与进程状态仅保存在本地证据。|
| 人工触发外部窗口最大化 | NOT_RUN | 自动校验和 release 编译不能证明真实目标窗口的鼠标操作；需要在单实例 release 中用已登记目标实际点击。 |

环境：Windows 11 Pro 10.0.22000 x64、Python 3.11.4、Node v22.23.4、npm 11.19.0、Cargo 1.93.0、rustc 1.93.0。命令结果和 build 元数据保存在被忽略的 `evidence/local/nextgen-2026-10-27/native-window-actions-extension.json`；未读取或记录 runtime descriptor、令牌、Obsidian 笔记或 TrafficMonitor 指标。

## 2026-10-27 B04-01 有类型状态事件

按连接注册/注销 `event.subscribe` / `event.unsubscribe`，只可订阅已加入世界的 `window.geometry_changed` 与 `window.visibility_changed`。事件带 `event_id`、`subscription_id`、world ID、source、可选 cause、sequence、window_revision 与最小 payload。读者仍只读；订阅断线、leave、destroy 时自动失效。高频状态经 per-world latest-state watch 合并；`interaction` / `world.deleted` 留在独立有界 occurrence 广播，慢消费者收到 `resync_required` 后断开。事件只用于观察，宿主不自动把事件映射为动作。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo fmt --all -- --check` | PASS | exit 0。|
| `cargo test --workspace` | PASS | 69 tests passed：core 43、desktop 13、server 13。包含 512 次 state notification 只保留每世界最新值且不占用 occurrence 队列、真实 WebSocket 订阅权限/取消/无自动动作回归。|
| `cargo check --workspace` / `cargo clippy --workspace --all-targets -- -D warnings` | PASS | 两项 exit 0。首次 check 捕获到同步 MutexGuard 跨 `.await` 的 Send 错误；把快照读取限定在 await 之前的作用域后复检通过。|
| `npm run check` | PASS | 24 Node tests + 10 offline contract/schema checks。|
| `python -m unittest discover -s tests -v` | PASS | 63 tests passed，包含 Python capability gate 与 bounded event queue coalescing。|
| `python skills/wincraft-provider/scripts/verify.py` | PASS | 19 个 Provider Skill 引用有效。|
| 真实 headless Rust WebSocket `lease_probe.py` | PASS | 36 checks：读者订阅仍无写权；geometry/visibility 类型状态、leave/destroy/unsubscribe 清理、租约栅栏和慢消费者 disconnect 均通过。临时描述文件随 headless 退出删除；未读取或记录令牌。|
| `npm run desktop:build` | PASS（构建）／NOT_RUN（启动） | 使用独立 target 构建成功；本机已有宿主进程时没有并行启动第二个托盘实例。|

修复记录：一次 WebSocket 测试用跨会话写者 lease 得到 `STALE_LEASE`，按内核真实拒绝码修正断言；事件实现的首轮编译发现 MutexGuard 跨 await，已修复。第一次 release target 放在 E: 后因空间不足失败；本机策略拒绝清理该次失败 target，未尝试绕过，改在 H: 独立 target 构建成功。检查时 E: 约剩 0.04 GiB，失败 target 占约 1.32 GB；没有触碰 E: 其他目录。

环境：Windows 11 Pro 10.0.22000 x64、Python 3.11.4、Node v22.23.4、npm 11.19.0、Cargo 1.93.0、rustc 1.93.0。脱敏命令摘要见忽略的 `evidence/local/nextgen-2026-10-27/window-events-b04-01.json`。真实 Tauri 窗口像素、托盘交互和 native UIA 不由 headless WebSocket 测试证明。
## 2026-10-27 提供者路线与原生窗口选择收紧

2026-10-26 平台演进交接包已核对并整合到 `docs/strategy/2026-10-26`；新增 [provider-journey.md](../provider-journey.md) 作为 Agent 提供者分层教程入口，未改变协议 0.3。

跨应用 `native_window_action` 的窗口选择已改为失败关闭：单一可见匹配直接执行；多匹配仅当前前台窗口也属于匹配集合时执行，否则返回要求收窄标题筛选的错误，不按枚举顺序盲选。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo fmt --all -- --check` | PASS | exit 0 |
| `cargo test -p wincraft-desktop native_window_action --no-fail-fast` | PASS | 3 tests passed，含多窗口歧义拒绝 |
| `cargo check -p wincraft-desktop` | PASS | exit 0 |
| `cargo test --workspace --no-fail-fast` | PASS | 70 tests passed |
| `npm run check` | PASS | 24 Node tests + 10 offline contract checks |
| `python -m unittest discover -s tests -v` | PASS | 63 tests passed |
| `python scripts/check_contracts.py` | PASS | offline schema/config consistency |
| `python skills/wincraft-provider/scripts/verify.py` | PASS | 19 provider-skill references |
| 当前 release 真实点击、托盘、DPI/多屏 | NOT_RUN | 仍需单实例 Windows 人工验收；自动测试不替代原生操作 |

脱敏命令摘要写入 `evidence/local/nextgen-2026-10-27/native-window-actions-selection-20261027.json`，未读取或记录 runtime descriptor、令牌、Obsidian 笔记或 TrafficMonitor 遥测。

## 2026-10-27 原生动作失败/路由回归

服务层新增两项 B04-02 回归：原生 Windows 动作返回失败时，不创建 pending action、不广播 provider interaction；context gesture 不触发点击专属的宿主 OS 动作，但仍按静态 `context_action` 发送 provider 事件。它验证的是宿主拒绝路径与事件顺序，不模拟 Windows API，也不代替真实前台拒绝验收。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo test -p wincraft-server native_window_action --no-fail-fast` | PASS | 3 个相关测试通过，包括 host capability gate、原生失败不派发、非点击来源保持 provider 路由。首轮夹具缺少 `context_action` 且使用了错误的 `Hub::read` 调用，按实际契约修复后通过。|
| `cargo test --workspace --no-fail-fast` | PASS | 72 tests passed：core 43、desktop 14、server 15。|
| `cargo clippy --workspace --all-targets -- -D warnings` | PASS | exit 0。|
| Windows 实际 SetForegroundWindow 拒绝与 Obsidian Workspace 点击 | NOT_RUN | 需要当前 Tauri release 的真实交互；此处未调用或伪造。|

本次证据在 Rust 自动测试输出中；未启动第二个宿主，未读取 runtime descriptor 或真实业务数据。
## 2026-10-27 B04-02 工作区语义锚点

协议 0.3 新增 `WindowSpec.anchor` / `WindowPatch.anchor` 和 `window_property:anchor` capability。provider 必须先切到 `geometry_control=provider`；人类控制下配置会返回 `HUMAN_GEOMETRY`。角落是当前解析 monitor work area 的四角，边距单位为逻辑像素，按该 monitor scale factor 换算，超出 work area 时夹取。Tauri 窗口适配器在位置应用时解析锚点，并在 `ScaleFactorChanged` 后按当前显示器重新应用。本机 Tauri API 没有显示器拔除专用事件，自动迁移必须继续实机验收。operator rescue 清除 anchor、返回 human geometry、撤销 writer lease。

`window.geometry_changed` 现在比较并携带最新 anchor；服务 fixture 特意含非空 anchor，离线 validator 注册 scene schema，确保引用本身被解析而非只验证 null 分支。

- `cargo fmt --all -- --check`：PASS。
- `cargo test --workspace --no-fail-fast`：64 PASS（core unit 5、core invariants 43、desktop 14、server 16）。
- `cargo check -p wincraft-desktop` 与 workspace Clippy `-D warnings`：PASS。
- `npm run check`：24 Node tests + 10 offline contract checks，PASS。
- Python suite：64 PASS；provider skill reference verifier：19 PASS。
- 独立隔离 target 构建的真实 Rust headless + `lease_probe.py`：38 checks PASS，覆盖 anchor capability、human 拒绝、provider 配置/快照回读和 anchor 状态事件。
- 真实 Tauri 显示器 DPI 像素、负坐标副屏、显示器拔除迁移及拖动仍 `NOT_RUN`。

脱敏记录见 `evidence/local/nextgen-2026-10-27/work-area-anchor-20261027.json`。临时 headless runtime descriptor 有一份残留在被忽略的隔离目录；没有读其内容或复制到证据/提交。
## 2026-10-27 B04-03 快捷键资源意图层

新增 `crates/wincraft-core/src/shortcuts.rs`，只实现可撤销的 session-scoped shortcut intent registry，不安装 OS hook、不监听键盘、不宣称全局热键已生效。注册表拒绝重复 chord、Windows 保留 chord 和无 modifier 的单键；支持按 chord unregister 与按 session revoke，冲突失败不会替换原 owner。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo test -p wincraft-core shortcuts --no-fail-fast` | PASS | 3 个新增测试：冲突不占用、session revoke 隔离、保留键/无 modifier 失败关闭 |
| `cargo test --workspace --no-fail-fast` | PASS | 82 tests passed（core unit 8、core invariants 43、desktop 14、server 17）；Hub disconnect 自动 revoke session shortcuts 的服务回归通过 |
| `cargo clippy --workspace --all-targets -- -D warnings` | PASS | exit 0 |
| Windows `RegisterHotKey`/IME/UIA/真实冲突 | NOT_RUN | 当前只完成核心意图层；接入 OS 前需用户授权与人工原生验收 |

回退边界：移除 registry 模块即可回到没有快捷键资源意图的旧行为；没有修改系统全局配置或注册任何后台键盘监听。
## 交接包规划、导出与运行时导入（2026-10-30）

当前契约检查会执行交接包 `docs/strategy/2026-10-26/tests` 的完整 unittest suite。2026-10-30 复核为 **40 tests passed**，覆盖 inventory 匹配/缺失/歧义/权限、过期与 generation、digest 稳定性、pack secret/path traversal/artifact rejection、adapter 不执行和旧验收结果失效。`tests/test_pack_export.py` 的 10 项通过、1 项 Windows symlink 创建不可用而跳过；拒绝 symlink 的检查仍保留。

`tools/pack/export_pack.py` 仅把显式指定的 `pack.json` 与引用的 blueprint JSON 写入 `.wcp`，不安装 Provider、不运行 adapter、不调用 Host。B06-03 现已补入 Rust Host 与内部管理器：受限解析 `.wcp`、只读生成计划、显式授权后重新规划、用户确认后逐世界创建、定向加入事件、幂等提交与有条件回退。它是独立 `0.4-preview.1` 能力，不扩展稳定 Protocol 0.3；Provider 必须声明 `world.import.accept`，Host 在 capability 中公布草案 schema、事件、排他写租约和本机确认要求。

| 验收 | 状态 | 证据范围 |
|---|---|---|
| B06-01-A1/A2/A3 配置包格式 | PASS（draft CLI export，L1-L2） | `.wcp` 仅含 pack 与引用的 blueprint；拒绝 binary、descriptor、lease、install hook、秘密字段和路径穿越；不执行 adapter。|
| B06-02-A1/A2/A3 纯规划器 | PASS（L0-L2 demo） | 必选/可选来源、权限与能力、歧义、digest、到期和无宿主副作用均由合成 fixture 覆盖；不扫描本机。|
| B06-03-A1 计划变化后失效并重新规划 | PARTIAL（Rust 行为测试，L1-L2） | generation 变化、授权后重新规划、过期与来源变化回归通过；新 release 管理器界面尚未实测。|
| B06-03-A2 取消不清空既有世界 | PARTIAL（Rust Host/manager 测试，L1-L2） | 取消预览/提交不会改变既有 worlds；release UI 的取消与重开尚未实测。|
| B06-03-A3 部分失败及真实回退 | PARTIAL（Rust Host/manager 测试，L1-L2） | 重复提交幂等；回退只删除账本吻合且未被后续改变/加入的资源，并报告保留项；Tauri release 中的成功/失败/回退交互尚未实测。|
| B06-04-A1/A2/A3 分享与新环境 | PARTIAL（静态 fixture/导出，L0-L2） | full/optional-missing/required-missing/no-grant 四种 inventory 已索引；合成 `.wcp` 只含 pack 与所引 blueprint、无凭据键或绝对用户路径。两独立用户环境、干净安装与重新授权仍 NOT_RUN。|

2026-10-30 Windows 本机 `npm run check:local` 退出码 0：UI 28 tests、离线契约一致性、Rust fmt/check/workspace tests/clippy、Python 176 tests（1 项因 Windows symlink 创建返回 `OSError` 而跳过）及 27 个 Provider Skill 引用检查均通过。增加 Host capability 断言后的定向 Rust 用例退出码 0。修复提交 `e3a4c4de4e345ac2230dec8f1aef6f62d049fc93` 的 Tauri release 已重新构建：`target/release/wincraft-desktop.exe`，13,279,232 bytes，SHA-256 `0FCC6BB2FD9E6FA462B1A04972180700995345F4B0F1BDA4C57B9749D2693E5A`。


阶段提交 `e3e8df4513841c22dd1ca7574e403991c9dbcb16` 的 Windows Actions run `40976867333` 通过格式、编译和 workspace tests 后，在 Clippy 1.99 的新 lint `chunks_exact_to_as_chunks` 失败。修复将 2-byte decoder 改为 `slice::as_chunks::<2>()` 并新增奇数长度/非法 hex/无效 UTF-8 回归；本机 `cargo fmt --check`、workspace Clippy 和 `npm run check:local` 均再次通过。修复提交 [`e3a4c4de`](https://github.com/exomind-team/WinCraft/commit/e3a4c4de4e345ac2230dec8f1aef6f62d049fc93) 的 [Windows Actions run 40979104886](https://github.com/exomind-team/WinCraft/actions/runs/40979104886) 已通过，耗时 11m26s；CI 不覆盖原生管理器 UI。

后续文档同步提交 `10d5881` 的 [Windows Actions run 40982406047](https://github.com/exomind-team/WinCraft/actions/runs/40982406047) 也已通过：Windows hosted source job 11m46s，Node 22、CPython 3.12.10、Rust 1.99.1；`npm ci`、Python requirements 安装与 `npm run check:local` 均成功。该次变更是文档/状态同步，CI 仍不覆盖 Tauri 原生管理器 UI。

预修复候选（功能代码对应 `e3e8df4`）曾以 `--open-manager` 启动，Computer Use 能枚举到“窗构 · 世界管理器”，但两次截图/可访问性读取均因 `GetCursorPos failed: 拒绝访问 (0x80070005)` 失败。按恢复规则已停止 UI 操作，没有点击或输入。修复提交 `e3a4c4d` 的新 release 已重建并启动（13,279,232 bytes，SHA-256 `0FCC6BB2FD9E6FA462B1A04972180700995345F4B0F1BDA4C57B9749D2693E5A`）；Python SDK 对该精确 Tauri Host 的只读 capability handshake 通过，未再次尝试 UI 采集。**原生管理器预览/授权/应用/回退仍为 NOT_RUN。** 详细命令、工具链、退出码、二进制哈希和失败证据见 `evidence/local/nextgen-2026-10-30/b06-03-pack-import-20261030.json`。

窗口状态读取失败后，另用当前 release 自己生成的本机 descriptor 做了只读 Python SDK hello/capability smoke：真实 Tauri Host 协商 `0.4-preview.1`，并返回 provider inventory 与 provider import 的预览契约、草案 schema、定向事件、声明 claim、排他写租约和本机确认要求。该请求未登记 inventory、未创建世界，也未调用导入；它只证明 Tauri Host 的真实协议握手，不证明 Manager UI。

供本机人工续验的合成 `.wcp` 流程见 [`docs/release/WINCRAFT_ALPHA1_ACCEPTANCE_CN.md`](../release/WINCRAFT_ALPHA1_ACCEPTANCE_CN.md) 的“B06-03 配置包导入人工验收”；测试包无业务数据，重建命令由仓库 exporter 生成到 `evidence/local/`。

**B06-03 保持 `IMPLEMENTED_UNVERIFIED`，A1/A2/A3 保持 PARTIAL。** 行为测试证明本地 Host/manager 规则；新 release 的预览、授权后重规划、应用、Provider 加入事件与动作回执、取消及回退 UI 尚未验证。不要把 release 构建成功或当前窗口存在写成 UI 通过。

**B06-04 保持 `IMPLEMENTED_UNVERIFIED`，A1/A2/A3 为 PARTIAL。** 当前仅证明格式/fixture/导出物的静态卫生；必须由两个独立用户环境分别读取同一个 `.wcp`，在来源缺失时明确解释且不下载/执行 Provider，再由每个用户单独选择并授权本地 Provider，才能关闭此任务。

## 2026-10-28 标题栏轴线与折叠尺寸

标题栏品牌、最小化和关闭图标改为内联 SVG，固定 viewBox 与尺寸，CSS 让图形盒和标题共享 48 px 标题栏的垂直中轴。折叠尺寸采用独立的本机展示覆盖：收起时按标题栏内容测量宽度、按可见内容测量高度；展开恢复收起前尺寸。临时 compact size 不覆盖提供者或用户保存的展开尺寸。`background_drag_enabled` 已接入空白非文本区域与 Tauri IPC，两侧都检查权限。

新增可选 `position_control` 并由 `window_properties` capability 宣告；缺省时继承旧 `geometry_control`，不改变旧提供者行为。此后可表达 provider 控尺寸、human 控位置，且拖动只更新 position、不改尺寸；operator rescue 恢复默认继承。`docs/engineering/ACCEPTANCE.md` 的 W08/W23/W25 已纳入拆分所有权、图标中轴、折叠宽高和无标题栏拖动标准。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `npm run check` | PASS | 28 项 UI 测试、离线契约与交接包检查通过；含 SVG/中轴、折叠宽度边界与背景拖动权限 predicate 测试。|
| `cargo fmt --all -- --check` | PASS | exit 0。|
| `cargo test --workspace --no-fail-fast` | PASS | 89 tests passed：core 8 unit + 45 invariants、desktop 18、server 18；含 provider-size/human-position split、background drag 权限及置顶默认/配置边界。|
| `cargo clippy --workspace --all-targets -- -D warnings` | PASS | exit 0。|
| Python suite / Provider Skill verifier | PASS | `python -m unittest discover -s tests -v`：78 tests；Provider Skill verifier：19 references。|
| 最新 Tauri release `lease_probe.py` | PASS | 对刚构建的 release 真实 Rust WebSocket host 完成 40 checks，包含 provider-size/human-position 栅栏、动态 patch、显隐、透明度、文本选择、背景拖动与 `always_on_top` 原生应用。|
| 独立 release 构建 | PASS | `target/release/wincraft-desktop.exe`，11,806,720 bytes，SHA-256 `0465752DB32BC4AAE37D7DA7D306F899FD8586F805A914B3EA0990C6FDD6963D`；阶段性产物及下载包见中文验收指南。|
| Release 启动 smoke | PARTIAL | 当前 release 管理器出现在 Computer Use 应用枚举中，刷新窗口选择后仍以 `failed to activate captured window` 失败；accessibility 文本可读，但没有取得可信的管理器截图或执行界面输入。托盘菜单仍待验收。|
| 默认置顶与提供者切换 | PASS（model + native report） | 普通 WindowSpec 和 manager 默认值为 true；lease probe 对真实 Tauri host 切换 false/true 并等待 native applied。普通窗口与其他 topmost 窗口的实际遮挡顺序尚未视觉核验。|
| 背景拖动授权门 | PASS（unit） | UI policy 测试文字/交互/选中/穿透/provider 位置控制拒绝；Rust command policy 测试标题栏与 background 拖动使用独立授权。Tauri 原生拖动尚未运行。|
| 折叠高度原生观察 | PASS（前一版 build） | 真实外心只读投影窗口从 480×1104 收到 480×50，标题栏高度通过；最新含宽度恢复的合并 build 尚未复测这个尺寸。|
| 折叠/展开原生尺寸 | PASS（前一 build） | Computer Use 观察到 `620×765 → 212×50 → 620×765`；本次 topmost 修改未触及折叠布局，最新 manager build 未复测。|
| 标题栏拖动与隐藏标题背景拖动 | NOT_RUN | 前一版 Computer Use drag 没有产生可测位置变化；本次重新授权后无法激活当前 release 管理器，没有再次拖动。需物理鼠标验收。|
| 展开恢复与图标中轴像素检查 | NOT_RUN（最新 build） | 静态 SVG/CSS 测试通过；本次 Computer Use 无法激活管理器窗口，未复测最新 build 的折叠、展开恢复或图标像素。|

## 2026-10-28 ExoMind 真实档案只读联调

用户曾明确授权一次本机只读 ExoMind 调研。该次只读检查没有调用时间块或任务写接口；profile、当前状态、返回数据和 RT build identifiers 不保留在公开记录中。

`examples/python/exomind_readonly.py` 曾通过 `GET /timeblocks/active` 完成单字段只读桥接 smoke；该证据不代表新的工作台 provider 已 live 验收。公开记录不含 profile ID、当前时间块内容、descriptor 或截图。

新的 `examples/python/exomind_workbench.py` 用本地状态循环映射 full、compact、mini，idle 是独立内容状态；仅发出 WinCraft 本地显示/隐藏动作。13 项 fixture 测试通过。尺寸使用来源 fallback 或明确标出的本地估值，稳态测量与 Windows z-order 仍待实机核验。

2026-10-28 本机以用户授权的本地连接信息完成一次 live GET 与 projection smoke；未调用 ExoMind 写 API，也未保存 profile、RT 地址、时间块字段或响应内容。随后以 Ctrl+C 停止 provider；其 `finally` 尝试销毁本地 WinCraft 世界，但本次重新授权的 Computer Use 无法激活管理器窗口，因此没有复核清理结果。本轮未通过 UI automation 操作其档位。

脱敏记录：`evidence/local/nextgen-2026-10-28/ui-titlebar-collapse-width-20261028.json`。本次 Computer Use 刷新选择后仍报 `failed to activate captured window`；读取到的 accessibility 文本不等于视觉或交互验收。托盘管理器打开、全局隐藏/显示、当前 build 折叠尺寸、标题栏拖动、置顶层级和剩余 W23 原生门保持 NOT_RUN。

## 2026-10-29 B07-03 类型状态槽

**Given** 两个互不重叠的 scope，scope A 创建一个有 schema 的共享槽并显式授权 scope B 读取；**When** 两个 owner CAS 使用同一 expected revision、reader 尝试跨范围读写，或父 scope/authority 被撤销；**Then** 只有一个 CAS 提交，其他 CAS 返回可诊断冲突，未授权写与撤销后的读取失败，子树撤销会清理或收回相关槽位权限。

`0.4-preview.1` 新增 `state.slot.create`、`set_readers`、`read`、`compare_and_set`、`delete`。槽位只接受 boolean、整数、有限 number、有界 string 和 enum，不接受对象/任意 JSON/指针/表达式。每槽 owner scope 单写；读者必须同时属于显式授权的 scope 且匹配 generation。槽位 revision 与 scope revision 分离。Host 对单次操作做同步内存仲裁，不跨网络等待持锁。0.3 descriptor 与稳定接口保持不变；Python SDK 在 capability 缺失、版本不符或访问语义不匹配时失败关闭。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `npm run check:local` | PASS | exit 0；28 Node UI tests、offline schema/contracts、Rust fmt/check/test/Clippy、88 Python tests、19 Provider Skill 引用。Rust workspace test 106 PASS：core unit 10、core invariants 59、desktop 18、server 19。|
| `cargo test -p wincraft-core --test invariants state_slot -- --nocapture` | PASS | 3 个专用回归覆盖竞争 CAS、读/写隔离、类型拒绝、scope 删除/父 authority 过期、每 scope 槽位与 reader 配额。|
| `python scripts/check_contracts.py` | PASS | exit 0；preview 请求 schema、五个正向方法 fixture、三个拒绝 fixture 均通过离线验证；方法仍只在 `0.4-preview.1` manifest 中。|
| `cargo build -p wincraft-server --bin wincraft-headless` | PASS | exit 0，构建当前 source 的 debug headless host。|
| `python examples/python/scope_probe.py --runtime "<isolated temporary descriptor>"` | PASS | exit 0；真实 Rust loopback WebSocket 验证显式 capability、并发 CAS 单胜单败、授权读取、错误类型原子拒绝、reader 撤销、槽位删除、父 scope 清理，以及 stable 0.3 拒绝 preview。慢消费者子用例停止一个 reader 的 WebSocket 接收、缩小接收缓冲区；owner 在此期间完成 64 次 scope 更新和后续 CAS。探针遵守 host 每连接 120 req/s 限额。|
| `npm run codegraph:sync` / `npm run codegraph:status` | PASS | 当前索引新鲜：70 files、1,682 nodes、5,499 edges。|
| Tauri 原生 UI、release EXE 和像素验收 | NOT_RUN | 状态槽不直接渲染；本任务验证范围为 core/server、preview SDK/schema 与真实 headless WebSocket。完整工作区 Cargo 检查已编译 Tauri target。|

撤销行为：删除 owner scope 会删除其槽位；删除 reader scope 会移除该 grant 并使槽 revision 前进；父 authority release/disconnect/expiry/rescue 会轮换所有 child generation/join key 并清空槽位。已有 provider 已读取的快照无法被追溯擦除，撤销保证之后的 host read 被拒绝。

CI 回顾：GitHub Actions 在 2026-10-28 连续 9 次于 `npm run check:local` 失败，日志共同显示 Windows 默认 `cp1252` 读取 UTF-8 夹具，以及 LF/CRLF checkout 使翻译源哈希误报；提交 `5e5f7e9` 显式固定 UTF-8 并按文本规范化换行，随后 Actions 更新到 Node 24 运行时。后续运行 `40801981651`、`40726526250` 均成功。本任务提交 `6eda1a0` 的 Windows hosted run `40809546638` 也成功，`npm run check:local` 步骤通过；job 用时 6 分 54 秒。该结果只证明自动检查，不是 Tauri 原生 UI 证据。

脱敏本地证据见 `evidence/local/nextgen-2026-10-29/b07-03-validation.json`。Headless 探针使用合成标识与临时 world；descriptor 仅由 Python client 为连接读取，临时文件在探针后删除，没有被复制或写入证据。回滚边界：移除 preview state slot 方法、capability、SDK helper 和 fixture 即可关闭高级共享；稳定 0.3 与已有 scope 结构能力不变。

## 2026-10-29 B07-04 多来源组合与故障隔离

**Given** 两个互不重叠的 provider scope，分别由 TrafficMonitor bridge 与通用 Obsidian Workspace 元数据 Provider 提供投影；**When** TrafficMonitor 的临时 x64 stage 被停止、其桥接快照转为过期；**Then** 仅 TrafficMonitor scope 更新为 stale，Obsidian scope 的投影保持不变，父 authority 仍独占窗口几何。

Core 新增可复现 seed 的 96 步 interleaving regression，交错执行两个 scope 的局部 props/data/CAS 写、越界 sibling 写与旧 revision 写。每步验证 owner scope generation、schema/value、reader grant generation、两边 namespace 与组件 props 独立；随后断开 scope A writer、用新会话/epoch 重加入、拒绝旧 lease，再删除 scope A 并验证其 owner slot 删除、scope B reader grant 清理。测试不依赖随机 crate，失败序列稳定可复现。

此处原来源联调不再作为当前通用 Obsidian Provider 的验收证据。新的公开组合探针读取本地插件生成的文件/工作区元数据快照，并用分离的 `traffic` 与 `obsidian` namespace 检查 sibling scope 隔离；本机插件实例与故障注入用例尚未重跑。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo test -p wincraft-core --test invariants deterministic_multiscope_interleavings_preserve_owners_and_sibling_business_state -- --nocapture` | PASS | seed 0x0b070403 的 96 步 interleaving 通过；跨 scope / stale revision 写不提交，disconnect 后 sibling scope data 与 subtree 不变，新 lease 取得更高 epoch，父删除清理 owner slot 和 reader grant。|
| `python -m unittest tests.test_multisource_composition tests.test_trafficmonitor_provider tests.test_trafficmonitor_staged_config -v` | NOT_RUN（旧结果撤回） | 先前该命令中的 Obsidian 来源实现已被通用插件样例替换；需要基于当前实现重跑组合 probe 后再登记 PASS。|
| TrafficMonitor bridge x64 build + isolated stage | PASS | `build_bridge.ps1 -Architecture x64` 与 `stage_demo.ps1 -EnableBridgeItem` 成功；version 1.8.6.0，`ReuseConfiguration=false`，没有 optional driver 被复制。原先的 stale stage process 被停止，新临时 stage 在故障注入后重启并再次确认 snapshot fresh/advancing。|
| Obsidian Workspace 本机插件快照 | NOT_RUN | 未在真实 Obsidian 窗口中加载当前插件样例。|
| `composition_probe.py` + real headless Rust WebSocket | NOT_RUN | 当前组合探针已切换为通用插件快照，仍需真实来源验收；合成结构测试不算 headless 实源 PASS。|
| `npm run check:local` | PASS | 28 Node UI tests、offline schema/contracts、Rust fmt/check/test/Clippy、90 Python tests 与 19 Provider Skill references 全部通过；Rust workspace 共 107 tests（core unit 10、core invariants 60、desktop 18、server 19）。|
| GitHub Actions run `40814128343` | PASS | Windows hosted `npm run check:local` succeeded; source job completed in 6m03s. This verifies the committed source checks, not native GUI acceptance. |
| B07-04 Tauri release/native UI | NOT_RUN | 此验收检查 scope 权限与业务数据隔离；窗口几何仍只由 root authority 控制。|

本地 evidence：`evidence/local/nextgen-2026-10-29/b07-04-validation.json`。原始 TrafficMonitor installation/config 没有改动；新 x64 copy 是临时 stage，provider bridge 文件只保存在该 stage。不要把它当成已完成安装升级；用户要求后续引导其把旧版正式升级换代。


## 2026-10-29 B08-01 统一活动模型与只读聚合器

**Given** 两个合成 Harness 实例，其中一个实例有父会话和两个子会话，另一个实例使用与前者相同的显示名/模型名；**When** 聚合器校验身份、新鲜度和父子结构并生成 Agent Board；**Then** 断线保持为 stale、未知保持为 unknown，父容器不与子任务重复计数，标签变化不合并实例，界面没有批准/写文件/继续执行动作。

`protocol/activity.schema.json` 是 `draft-2026-10-29` 提案，不是 protocol 0.3 host API。身份键为 `device_id / provider_id / source_instance_id / session_id`；freshness 单独表达来源时效；完整父子树要求缺父项、循环和重复身份失败关闭。场景只携带供本地 renderer 使用的有限名称、项目标签和短摘要，不把 source/session/task ID、完整路径、模型名或原始来源状态复制进宿主数据。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest tests.test_agent_activity_board -v` | PASS | 9 tests：freshness 条件、过期投影、稳定身份、叶节点去重、父树完整性、空控制能力、场景无交互动作和 provider cleanup cancellation。|
| `python scripts/check_contracts.py` | PASS | 校验 draft 活动 Schema、4 条合成记录及 disconnected-as-idle / approval-capability 两种负例。|
| `npm run check:local` | PASS | 28 Node UI、107 Rust workspace、99 Python tests；fmt/check/Clippy、离线契约和 27 个 Skill references 全部通过。|
| Agent Board provider + Tauri release | PASS | 使用真实 release Tauri host 呈现合成快照；UIA 确认叶会话/等待/断线计数和父子顺序，scene 只有只读组件；没有连接 Harness 数据源。|
| provider world cleanup | PASS | 自然到期与交互式 PTY Ctrl+C 都确认销毁唯一测试世界，管理器恢复 0 个世界。非 TTY 执行器的强制 Ctrl+C 会直接杀进程并留 stale 世界；该测试副本随后由管理器关闭。|
| GitHub Actions run `40818791865` | PASS | B08-01 commit `fce1c87` 的 Windows source job 全量 `npm run check:local` 成功，用时 6m03s；不代表真实 Harness adapter 或审批 UI 已验收。 |
| 真实 Harness adapter / approval flow | NOT_RUN（CLI 适配进行中） | B08-02 已加入 Claude `agents --json` 与 Codex app-server `thread/list` 的只读 adapter；Codex CLI 状态库与 Codex App connector 不同源，故最终适配及 approval flow 尚未验收。|

本地脱敏证据：`evidence/local/nextgen-2026-10-29/b08-01-validation.json`。原始 Harness、Obsidian 笔记和外心业务数据均未读取；本任务 fixture 全部为仓库内合成数据。

## 2026-10-29 B09-01 设备消息信封与去重边界

**Given** 合成设备消息经带外 `TransportReceipt` 到达，其中包含乱序序号、重复 message ID、过期 TTL、撤销来源和 relay trace；**When** inbox 验证消息契约与接收回执；**Then** 只按 origin 身份去重，乱序按 source sequence 排序，重复不增加待办计数，过期/撤销消息从活动投影移除，relay trace 不会成为 origin identity。

`protocol/device-message.schema.json` (`draft-2026-10-29`) 只描述有限摘要、origin、序号、TTL、provenance 和 redaction。认证信息由外部 transport adapter 带外提供；本例不实现认证、WSS、Android 通知监听或多跳网络，也不打开公网监听。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest tests.test_device_inbox -v` | PASS | 9 tests 覆盖重复/乱序、TTL、撤销/replay、带外认证、relay 与 origin 分离、raw body 拒绝和只读场景。|
| `python scripts/check_contracts.py` | PASS | device-message draft schema、3 条正例及 raw-body/missing-origin 负例均通过。|
| `npm run check:local` | PASS | 28 Node UI、107 Rust workspace、108 Python tests；fmt/check/Clippy、离线契约和 27 个 Provider Skill references 全通过。|
| Device Inbox provider + Tauri release | PASS | release 宿主显示合成摘要与 todo 计数；scene 无按钮/输入/原生动作；PTY Ctrl+C 后只销毁自己的临时 world，manager 回到 0 个世界。|
| 真实外部 transport / Android 通知 | NOT_RUN | 没有用户选定的真机/应用/认证通道；本任务仅验证可注入的认证边界，不声称真实通知已读取。|

本地脱敏证据：`evidence/local/nextgen-2026-10-29/b09-01-validation.json`。没有读取真实通知、手机数据、消息正文或认证材料。

## B08-03 全局面板切换验收计划

2026-10-29 用户补充：一个全局悬浮窗按需切换 Claude Code、Codex CLI 与 Codex App 三种独立来源；Codex App 行显示会话名、状态、项目与最近 Agent 输出，来源健康与最近更新时间常驻可见，详情渐进披露。Codex App connector 与 Codex CLI state DB 是不同来源，不能合并计数。本机 CLI adapter 只读取明确列出的只读状态接口，不扫描任意会话日志。合成总览 A6/A7 已通过；真实 Codex App 快照桥接、三来源原生呈现与当前 A4/A5/A8 保持 `NOT_RUN` 或 `BLOCKED`，详见下方 B08-02 记录。

## 2026-10-29 公开仓库脱敏预检

| 检查 | 结果 | 范围与限制 |
|---|---|---|
| Gitleaks 8.30.1 历史扫描 | PASS（凭据规则） | 官方发布校验和已核对；扫描全部可达历史（`--all --full-history`），退出码 0，0 条凭据规则命中。 |
| Gitleaks 当前工作目录扫描 | FAIL（仅忽略的本机证据） | 523 个文件副本中有 5 条 `generic-api-key` 命中，全部位于 `.gitignore` 排除的 `evidence/local/` 旧 `.runtime.json` 测试描述文件。匹配值未写入输出或证据；这些文件不是可分享内容。 |
| 本阶段暂存差异定向脱敏扫描 | PASS（scope-limited） | Gitleaks CLI 当前未安装；自定义脱敏扫描检查暂存新增行中的凭据样式、Windows 用户路径、runtime descriptor 名称及本轮实际 Codex thread ID/标题/输出，均无命中。此窄扫描不等价于完整 Gitleaks。 |
| 跟踪文件与 Git 历史个人路径 | FAIL（公开准备） | 当前跟踪文件不含本机用户目录路径；历史提交 `5d64341c9e69` 的旧验收文档曾包含一条本机绝对路径。该提交属于此前公开的历史。公开前需清理/替换历史，再验证新候选历史。 |
| 已跟踪截图 | PASS（内容审查） | `evidence/assistant-run/manager-preview.png` 与 `world-preview.png` 只呈现明确标注的浏览器合成数据；桌面应用图标为通用图形。 |
| 当前仓库公开状态 | BLOCKED | `exomind-team/WinCraft` 当前为私有。用户有未来公开意向，但尚未授权本轮改可见性。忽略证据中的描述文件和历史个人路径均须先处置。 |

本预检只覆盖 Gitleaks 8.30.1 默认规则及上述路径审查，不是全面隐私审计、依赖审计或发布授权。扫描未输出凭据值；扫描临时副本的清理状态只记录在默认忽略的本机证据索引中，不作为产品验证通过项。

## 2026-10-29 Tauri release 窗口状态复验

对 `target/release/wincraft-desktop.exe` 中的管理器与临时合成空白世界执行 Computer Use。此前 2026-10-28 记录的“最新 build 未复测”只反映当日状态，以下结果更新本组 UI 场景：

| 场景 | 状态 | 观察结果 |
|---|---|---|
| 标题栏折叠/展开尺寸（W23） | PASS | Computer Use 的窗口截图尺寸由 `412×222` 收敛到 `166×50`；展开并稳定复查后恢复 `412×222`。折叠态仅剩标题栏，宽度与高度都收紧。 |
| 隐藏后由管理器恢复（W18） | PASS | 隐藏后管理器状态显示“窗口隐藏”并提供“显示窗口”；点击后同名世界重新可见，管理器报告“窗口显示”，尺寸 `412×222`。 |
| 临时世界清理 | PASS | 两个合成空白世界均通过世界关闭操作清理；最终管理器显示 `0` 个开放世界。 |
| 托盘全局隐藏/显示、置顶层级、点击穿透救援、多 DPI/多屏 | NOT_RUN | 本轮未触发这些场景，不沿用其他用例结果。 |

本轮未保存截图：管理器画面包含本机 runtime 描述文件路径；验证记录只保留合成场景、状态和截图尺寸，不记录世界 ID、窗口系统 ID 或描述文件内容。尺寸是 Computer Use 的窗口截图像素，不代表跨 DPI 的物理像素。

## 2026-10-29 B08-03 单窗口 Agent 活动纵览原型

**Given** 仓库内合成的 Codex/Claude Code 活动投影；**When** 用户切换来源、打开一个 Claude 会话详情并返回；**Then** 同一窗口保留当前来源状态、显示新鲜度与确认时间，所有按钮只执行 `view.*` 本地导航，不批准、不写业务数据、不继续 Agent 会话。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Agent Board + Global Overview Python tests | PASS | 当前 27 项专项测试覆盖身份/来源隔离、Codex App 标题/状态/项目/输出投影、source health/freshness、限量预览、空态、分页、过期 detail action 拒绝、回执和清理。 |
| `npm run check:local` | PASS | 退出码 0；28 项 Node UI、138 项 Python 测试通过，Rust workspace fmt/check/test/Clippy、离线契约和 27 个 Provider Skill 引用检查通过。 |
| `python scripts/check_contracts.py` | PASS | draft activity/schema fixtures 与仓库内 Python 语法检查通过；本项不验证真实 Harness 来源。 |
| `python skills/wincraft-provider/scripts/verify.py` | PASS | 27 个仓库内 Provider Skill 路径可解析。 |
| 当前 Windows Tauri release + synthetic provider | PASS（L3-L4 UI） | 本地 Rust/Tauri WebSocket 真实连接；Computer Use 看到总览 `520×421`、Claude 列表 `520×422`、Codex 列表 `520×512`、单会话详情 `520×477`。来源切换、详情、返回均出现动作确认；截图中没有可见窗口级滚动条。 |
| 临时世界清理 | PASS（真实 release 闭环） | 关闭世界后 provider 收到顶层 `world.deleted` 并自行退出，退出码 0；管理器最后显示 `0` 个开放世界，无人工中断或重复销毁请求。 |
| 三来源 live adapter 总体验收 | PARTIAL | Claude Code 与 Codex CLI 的只读状态可同窗显示；Codex App connector 元数据已由 Agent 读取，但实际 snapshot 没有进入 release Provider。Codex App live rows 和原生链接状态详见下方 B08-02。 |

脱敏本地记录：`evidence/local/nextgen-2026-10-29/cua-window-state-20261029.json`。该记录验证的是 synthetic PASS；实时 CLI 来源另见 B08-02 记录，不能把两种证据合并成 Codex App 连接已完成。

### 2026-10-29 Codex App 会话行可见性补充

**Given** 合成 Codex App 会话快照及来源读取年龄；**When** 生成 Codex App 来源页；**Then** 会话标题、状态、项目和最近输出对应独立 renderer 组件，输出使用正文尺寸，页面总显示来源新鲜度及成功读取年龄。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest discover -s tests -p test_agent_live_sources.py -v`、`python -m unittest discover -s tests -p test_agent_global_overview.py -v`、`python -m unittest discover -s tests -p test_agent_activity_board.py -v` | PASS | Python 3.11.4；18 + 9 + 9 项合成定向测试全部通过，退出码均为 0。覆盖四项会话字段、新鲜度秒数、输出字号和分页/来源行为。工作树基于 `283c1b8` 且含未提交改动。|
| 当前改动的 release 窗口像素检查 | BLOCKED | Computer Use 两次按重新枚举对象获取管理器窗口都返回 `window id was not found`；未重用旧句柄或坐标，因此本次没有截图级证据。|
| 实际 Codex App 快照进入 Tauri release Provider | BLOCKED | 这次改动只验证合成快照的 renderer 组件树；真实 connector-to-Provider stdin relay 仍未打通，不能据此声称真实会话已呈现。|

## 2026-10-29 `world.deleted` 事件封套与 Provider 清理

Rust transport 实际发送的世界删除 occurrence 将 `world_id` 放在事件顶层；`interaction` 的世界身份则位于 `data`。统一的 `client.event_world_id()` 同时读取两类封套，Provider 仍必须将身份与本进程创建的 world 精确比较。修正了教程、Popup、主题、TrafficMonitor、Obsidian Workspace、ExoMind workbench、Focus Demo 与 Global Overview 的关闭事件分支；不改变 0.3 wire 格式。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| 事件身份 helper 单测 | PASS | 顶层 `world.deleted`、嵌套 interaction、缺失/错误身份均有回归；无匹配 world 身份时 fail closed。 |
| Provider 关闭路径专项测试 | PASS | Global Overview 测试模拟顶层删除事件后停止，不再重复调用 `world.destroy`；Popup 对规范顶层与兼容嵌套两种样例均通过。 |
| 清理结果不确定路径 | PASS（只读复核） | manager 已删除 world 时 `world.destroy` 返回 `NOT_FOUND`，Provider 用 `world.snapshot` 确认缺失后报告清理完成；未知/其他错误仍保留不确定状态。 |
| Tauri-hosted `lease_probe.py` | PASS | 退出码 0，共 41 项检查；`world_deleted_top_level_id_reaches_original_member` 通过，管理器最终显示 0 个开放世界。第一次重跑因 probe 自身漏传 `checks` 参数触发 `NameError`；修复探针后通过。 |
| Global Overview manager-close lifecycle | PASS | 当前 release 关闭合成世界后，provider 收到顶层删除事件并以退出码 0 正常停止；没有再调用 destroy，manager 归零。 |

脱敏本地证据：`evidence/local/nextgen-2026-10-29/b08-03-global-overview-validation.json`。这修正避免了本地 manager 已关闭窗口而 Provider 仍等到时限后误报清理不确定。

## 2026-10-29 B08-02 Claude Code、Codex CLI 与 Codex App 三来源适配（真实 App 桥接阻塞）

**Given** 三种独立来源：Claude Code `agents --json`、Codex CLI app-server `thread/list`、以及授权 Agent 经 Codex App connector 提供的快照；**When** Live Provider 汇总；**Then** 每个来源有独立身份、状态和最近成功读取时间，Codex App 页面逐项提供标题、状态、项目和最近输出，缺少桥接数据时明确等待，不把 Codex CLI 查询成功等同于 APP 会话在线。

Claude `agents --json` 的含义是后台 Agent 记录，不是全部交互式 Claude 会话。当前查询成功返回 2 条 `blocked` 后台 Agent 记录，同时本机没有 Claude 命名进程；界面显示“CLI 可查询 / 后台 Agent 阻塞”，不宣称 Claude Code 会话在线。Codex CLI 仍只读本机状态库且固定 `useStateDbOnly=true`。本次 Codex App connector 只读取 `list_threads`/`list_projects` 元数据并对 5 个 active 项读取限长 Agent 消息；共观察 38 个 Codex 项（5 active、2 idle、31 notLoaded），没有保存标题、项目名、内容或原始 ID。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Claude Code `agents --json` / Codex CLI `thread/list` | PASS（L1-L2） | Claude CLI 查询成功，当前返回 2 个 blocked 后台 Agent；Codex CLI `useStateDbOnly=true` 返回 0 条。本地状态没有扫描 JSONL 或完整会话日志。|
| Codex App connector 只读枚举 | PASS（来源读取） | `list_threads` 与 `list_projects` 返回独立于 Codex CLI state DB 的 Codex App 数据；active Agent 消息只读限长，不读取完整 turn/tool history。|
| 三来源规范化、独立健康、新鲜度与 Codex App 四字段行 | PASS（L1-L2） | `tests.test_agent_live_sources` / `tests.test_agent_global_overview` 共 27 项定向测试通过；覆盖 App 标题/状态/项目/最近输出、受限链接、来源失败隔离、上次成功时间与 CLI/App 状态映射。|
| `npm run check:local` | PASS | 28 Node UI tests、116 Rust workspace tests、145 Python tests、fmt/check/Clippy、离线契约与 27 个 Provider Skill 引用均通过，退出码 0。|
| `npm run desktop:build` | PASS | 提交 `32c8eee` 后重建 Windows release `target/release/wincraft-desktop.exe`；12,429,312 bytes，SHA-256 `77725D06515DAFFCBAAA7CFA928DDFF7D51B5B022DA8BA46A51D51547B68932E`。|
| GitHub Actions run `40852232278` / commit `6a44c00` | PASS | Windows hosted `npm run check:local` 通过，用时 11m26s；workflow 不启动 Tauri 窗口，也不替代本机原生/人工验收。|
| GitHub Actions run `40853925244` / commit `d5987b3` | PASS | 后续文档同步提交的 Windows hosted `npm run check:local` 通过，用时 11m12s；不增加原生 UI 验收证据。|
| GitHub Actions run `40876095509` / commit `32c8eee` | PASS | Windows hosted `npm run check:local` 通过，用时 11m42s；workflow 不启动 Tauri 窗口，也不替代原生 UI 验收。|
| Tauri release + 合成 ASCII bridge smoke | PASS（L3 可访问性） | Computer Use accessibility tree 在真实 release 窗口中看到会话名、状态、项目和输出四项，以及来源健康与相对更新时间。样例内容为合成 Smoke/Demo，不代表真实 Codex App 会话。|
| `--open-manager` release 启动 | PASS（L3，提交前同源码工作树） | Computer Use 枚举到真实管理器窗口；未运行 Vite 代理。随后从提交 `32c8eee` 重建了最终 EXE；默认不带参数的 tray-only 启动与托盘菜单未在本轮复验。|
| 同源码 release + PTY JSONL 合成快照 | PASS（L3 UIA） | `live_provider.py --codex-app-bridge` 接入真实 Rust/Tauri WebSocket；通过保持 stdin 的 PTY 注入合成 Codex App snapshot，UIA 树显示会话名称、状态、项目和最近 Agent 输出。超过 TTL 后显示断线/陈旧；UIA smoke 在提交前同源码工作树的 EXE 上完成，未把合成字段记作真实会话接入。|
| Codex App connector 实际快照进入 release Provider | BLOCKED | 经 Codex App connector 读取当前会话元数据/最近输出后，尝试送入持续 Provider；当前 release UI 仍显示等待桥接，未证明真实 connector payload 到达。合成 PTY 快照只验证接收与渲染路径，不能替代真实 Agent relay。|
| Codex App 原生深链接点击与目标加载 | NOT_RUN | 只通过单元测试验证 UUID-only `codex://threads/<UUID>` allowlist；本轮没有确认实际点击和目标会话加载。|
| Pixel screenshot / 最新来源列表的人工观感 | NOT_RUN | Computer Use 可读到当前 release 的 accessibility tree；其 native screenshot capture 返回黑帧，本轮没有可审阅的像素截图。|

本地脱敏证据：`evidence/local/nextgen-2026-10-29/b08-02-three-source-ui-validation.json`。不保存 runtime descriptor、来源标题、项目名、工作目录、提示词、输出片段或原始 thread ID。B08-02 整体标为 `BLOCKED`：来源卡片与 synthetic release 渲染已验证，真实 connector relay 和原生深链接仍待完成。

### 2026-10-29 三来源会话卡片字段统一

**Given** Codex CLI、Claude Code 与 Codex App 的不同只读快照；**When** 打开任一来源会话页；**Then** 每张卡片都显示名称、状态、项目与来源能确认的最新文本，并持续区分 Agent 输出、未标注发言方的会话预览和来源未提供的输出。

| 来源字段 | UI 呈现 | 边界 |
|---|---|---|
| Codex App `title/status/project_label/last_agent_output` | 名称、状态、项目、`最近 Agent 输出` | exact connector excerpt；仅短预览进入卡片，完整摘要不入 evidence。|
| Codex CLI `name/cwd/preview` | 名称、状态、工作目录末级项目名、`会话预览（发言方未标注）` | `thread/list` preview 不能确认发言角色，因此不叫 Agent 输出；不读 turns 或 rollout 文件。|
| Claude Code `name/state/cwd` | 名称、状态、工作目录末级项目名、`来源未提供最近 Agent 输出` | `agents --json` 没有输出字段；不从日志或其它会话推断。|

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest tests.test_agent_live_sources -v` | PASS | Python 3.11.4；21 项通过，退出码 0。覆盖三来源卡片字段、角色标签、身份/路径脱敏与新鲜度。|
| `python -m unittest tests.test_agent_global_overview -v` | PASS | 9 项通过，退出码 0；来源切换、详情、分页和 cleanup 回归通过。|
| `python scripts/check_contracts.py` | PASS | 退出码 0；活动 draft schema 接受来源预览类型，离线契约及 fixtures 通过。|
| `npm run check:python` | PASS | Python 3.11.4；145 tests 通过，27 个 Provider Skill 引用通过，退出码 0。|
| `npm run codegraph:sync` / `npm run codegraph:status` | PASS | 最后同步 1 个后续变更文件；85 files、2,136 nodes；索引 current。Node.js v22.23.4。|
| 同源码 release + PTY synthetic snapshot | PASS（L3 UIA） | `npm run desktop:build` 后独立 EXE 启动；真实 Rust/Tauri WebSocket provider 注入合成 Codex App snapshot，Computer Use accessibility tree 看到会话名称、状态、项目、Agent 输出和 TTL stale 状态。输入/输出值只用合成数据；像素截图不可用，因此不作截图级结论。|
| 当前 release manager | PASS（启动/可访问性） | `target/release/wincraft-desktop.exe --open-manager` 启动后 Computer Use 读取到管理器窗口；该参数是显式自动化入口，不证明默认 tray-only 启动或托盘退出。|
| 当前 `npm run check:local` | PASS | 28 Node UI、116 Rust workspace、145 Python tests；fmt/check/test/Clippy、离线契约、27 Provider Skill references 均通过，退出码 0。|
| 当前 `npm run desktop:build` | PASS | 提交 `32c8eee` 后重建 `target/release/wincraft-desktop.exe`，12,429,312 bytes，SHA-256 `77725D06515DAFFCBAAA7CFA928DDFF7D51B5B022DA8BA46A51D51547B68932E`。当前 hash 尚未重新做像素复验。|
| Codex App connector 当前会话进入 release Provider | BLOCKED | Agent 读取了当前 Codex App 会话字段并尝试经 PTY 发送受限快照，但 release UI 仍显示“等待 Agent 桥接”；不声称真实会话已显示。真实 UUID 深链接仍 `NOT_RUN`。|
| 当前 release pixel screenshot | NOT_RUN | Computer Use accessibility tree 可读；Tauri screenshot API 返回黑帧，没有可审阅的像素证据。|
| 临时 Provider/Host 清理 | PARTIAL | PTY Provider 收到 Ctrl+C 并确认销毁自己的 world；一次 stdin 已关闭的早期测试留下同标题 stale world，随后 WinCraft host 停止。一个匹配该已停止 Host PID 的本机 runtime descriptor 仍待清理；路径与内容未写入证据。|

本地实现测试使用合成字段；本机 CLI 只读 shape 检查只返回字段名/类型及非文本计数，不保存会话值。Codex App 真实快照桥接仍 `BLOCKED`，因此合成测试不代表真实 APP 会话已经进入悬浮窗。

### 2026-10-29 Codex App 快照采集时刻与 TTL 边界

**Given** 授权 Agent 送来带 `captured_at` 的 Codex App 快照；**When** 快照到达时距采集正好 30 秒；**Then** 来源健康仍表明已桥接，但会话和来源新鲜度都为 stale、年龄为 30 秒。未来时间戳失败关闭；旧格式缺少时间时回退为本机接收时刻。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest discover -s tests -p test_agent_live_sources.py -v` | PASS | Python 3.11.4；20 项定向测试全部通过，退出码 0。新增测试确认迟到快照不被当作刚更新、TTL 边界一致、格式错误/无时区/未来时间戳产生来源限定错误；数据全为合成样例。|
| `npm run check:python` | PASS | 140 项 Python 测试及 27 个 Provider Skill 引用检查通过，退出码 0。|
| `python scripts/check_contracts.py` | PASS | 离线 JSON/TOML、schema/fixture、Python 语法和 handoff 资产一致性检查通过，退出码 0。|
| 真实 Codex App 快照进入当前 release Provider | BLOCKED | 本轮管理器窗口句柄在两次重新枚举后仍无法稳定绑定；未取得 runtime descriptor，也未尝试猜端口或路径。既有 stdin relay 阻塞仍未解除。|

## 2026-10-29 B09-02 Android 设备可用性探查

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `adb devices -l` | PASS（仅设备可见性） | 命令成功，当前有 1 台在线设备、1 台离线设备；设备 ID 与型号未保存。未枚举应用、请求通知权限或读取通知。|

B09-02 保持 `BLOCKED`：用户尚未选择要读取的 app/source，也未授予通知权限。后续只能在明确选择与授权后读取脱敏摘要；不把合成信封结果当成 Android 验收。

## 2026-10-29 Agent Activity 三来源会话卡片与输出增量

**Given** Codex CLI、Codex App、Claude Code 的独立只读会话投影；**When** 打开默认总览或某个来源页；**Then** 会话卡片按 Codex App 截图的密度显示名称、状态、项目与可归因的最近 Agent 输出，较长内容通过来源页/详情渐进披露。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest tests.test_agent_live_sources tests.test_agent_global_overview -v` | PASS | 38 项定向行为测试通过。覆盖三种来源同一张卡片上的四个字段、Codex Desktop local-state 回退/connector 去重合并、未知状态不计作运行、rollout UUID 匹配、敏感文本脱敏、Codex 最近四线程读取上限/进程内缓存，以及 Claude 日志尾部只取 assistant 文本。 |
| `npm run check:local` | PASS | 退出码 0：28 项 Node UI 测试、116 项 Rust workspace 测试、154 项 Python 测试；Rust fmt/check/Clippy、离线契约与 27 个 Provider Skill 引用检查通过。 |
| 本机只读来源查询 | PARTIAL | Codex CLI app-server 与 Claude `agents --json` 查询可返回状态；本机 Codex CLI 没有可供验证的会话。Claude 返回的当前 session IDs 未与 `~/.claude/projects` 中 transcript 文件名匹配，因此没有真实 Claude Agent 输出被显示或保存。 |
| Codex Desktop local-state fallback | PASS（合成与本机只读） | SQLite read-only 查询只选 `originator=Codex Desktop` 的有限线程；标题/项目进入同一会话卡片，没有权威运行状态时显示未知。session meta UUID 匹配后才从最近四条 rollout 尾部提取 Agent 消息；MCP bridge 对同一 thread ID 优先并不产生重复卡片。 |
| 本机 Codex Desktop state DB / rollout smoke | PARTIAL | 本机只读查询发现 Desktop-originator 行并触发 128 行上限；本次最近四条有界 rollout 尾部没有找到可呈现的 `agent_message`，状态继续显示未知。没有显示或保存线程标题、路径、ID或消息正文。 |
| Codex App MCP snapshot → live Provider | PASS（真实本机协议数据） | 当前 Codex App `list_threads` 与四条 `read_thread` 的有界消息快照经 stdin 进入独立 Provider；Provider 汇总报告 Codex App 来源 online/partial，随后临时世界清理确认。没有保存快照或输出片段；这证明真实数据到达 Provider，不证明像素布局或点击深链接。 |
| 当前源码 release 的可见 UI | NOT_RUN | 本轮没有重建/重启 release 窗口或采集像素截图；Computer Use 恢复捕获失败，错误为 `failed to activate captured window`。现有 Tauri 进程仍在运行，Python scene 结构与来源映射由定向测试验证。 |
| Codex App 标题深链接点击/目标加载 | NOT_RUN | Host 宣告能力并通过 UUID allowlist 的单测；本轮未点击真实 App thread 链接或确认目标会话加载。 |
| Popup-Ask `surface_opacity=0.92` | PASS（代码/单测） | `npm run check:local` 中的 Popup 窗口规格回归通过；本轮未重新构建或实际打开新规格的 release Popup。 |
| CodeGraph / diff 检查 | PASS | `npm run codegraph:sync` 无待同步文件；`npm run codegraph:status` 为 current（85 files、2,183 nodes）；`git -c core.whitespace=cr-at-eol diff --check` 退出码 0（工作树含 CRLF 文件）。 |

来源输出只在 Provider 进程内短暂保留、裁剪与脱敏，不写入仓库、日志或证据。Codex CLI 的 `thread/read` 响应可能带有更早 turns，但只保留最多四个最近线程中的最后一条 `agentMessage`；`thread/list.preview`（通常是初始用户消息）不会显示。Claude 只读取唯一匹配 session ID 的日志尾部。无输出或身份无法匹配时 UI 明示不可用，不将用户提示、工具返回或其他会话内容伪装成 Agent 输出。Codex App 一次性 MCP 快照到 Provider 已实测；持续自动 relay、release 像素/深链接验收和 Claude 实际 transcript 映射仍未验收。

## 历史对照：2026-10-29 TeamSense 本机 Codex 数据源

**Given** TeamSense 既有 Codex 本机采集代码与其 App 用量静态调查；**When** 对照 WinCraft 的会话/用量来源；**Then** 区分本机 rollout 用量、会话 metadata 与账号额度，不把其中任一项冒充实时 Agent 状态。

| 检查 | 状态 | 结论 |
|---|---|---|
| Codex rollout 与 state SQLite 采集实现 | PASS（源码审阅） | TeamSense `codex-usage-collector` 扫描 `sessions` / `archived_sessions` 的 JSONL，只解析 `event_msg.token_count`，用只读 `state_*.sqlite` 查询会话名、cwd、模型、source 与时间；游标状态本机持久化。它不读对话正文、Agent 输出或实时运行状态。 |
| Codex 账号额度采集 | PASS（源码/契约审阅） | 独立 `codex_quota` 模块从本机 `auth.json` 在内存中取 access token/account ID，读取 `/backend-api/wham/usage`，再核对请求期间账号是否切换；报告不含访问令牌。该私有 quota 路径与 rollout 历史分开，不等于 Codex App 分析图表 API。 |
| Codex Desktop 静态分析 | PARTIAL | TeamSense 调查文档记录了 App bundle 中的模块及若干相对 API 路径；没有实际请求验证个人账号图表端点、完整响应 Schema 或更新时间。现有本机采集器没有实现这些 analytics 路径。 |
| TeamSense 是否是实时会话卡片来源 | NO（当时的证据边界） | TeamSense 的 quota/usage collector 与 WinCraft Agent Activity 是不同用途；本机用量 collector 不提供实时逐会话状态。后续 WinCraft 采用独立的 process + local-file reader，不再依赖 App snapshot bridge。 |

本次只读审阅了 TeamSense 源码、设计记录与本机 Codex 状态数据库字段；没有读取 `auth.json`、修改 TeamSense 或对 TeamSense 服务发起写入。TeamSense 的本机 quota 方法与 session metadata 方法彼此分开，分别可作为后续 WinCraft Agent Activity 与 TeamSense quota HUD 的参考；它们不代表 TeamSense 服务已接入 WinCraft。

### Codex Desktop 本机元数据回退场景

**Given** 本机 Codex `state_*.sqlite` 中唯一标记为 `originator=Codex Desktop` 的线程元数据，**When** Codex App 进程在线或离线而本机数据目录可读，**Then** 总览显示脱敏会话名与项目；进程状态独立显示，缺少逐会话权威状态时显示“状态未知”，只有 rollout 中精确匹配 `session_meta` 的 Agent 消息才显示为最近 Agent 输出。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Codex Desktop `state_*.sqlite` local-state adapter | PASS（合成与本机只读） | SQLite 以 read-only/query-only 打开；只选 `originator=Codex Desktop`、最近有界行、非 archived 记录。title/name 与 cwd 末级项目进入会话卡片，原始路径/ID不进入 scene；没有实时 App status 时明确为未知。本机查询因来源数量到达上限标 partial。 |
| rollout 尾部 Agent 输出 | PASS（合成） / PARTIAL（本机） | 只接受 sessions/archived_sessions 中以 `rollout-*.jsonl` 命名、且头部 `session_meta.payload.id` 与线程 UUID 匹配的文件；最多读取尾部 1 MiB，仅抽取 `event_msg.agent_message` 或 `task_complete.last_agent_message`，输出裁剪/脱敏并只保存在进程内。本机最近四条有界尾部未找到可呈现 Agent 消息，故真实输出仍不可验证。 |
| 旧 connector 与本机状态合并 | 历史实现，已移出当前 runtime | 该纯合成路径曾验证同 ID 去重；2026-10-30 用户改为本机进程/磁盘采集后，不再需要 connector bridge，相关 provider stdin 通道与合并函数已从当前 runtime 删除。 |
| 当前源码 release / 实时 APP 卡片 | NOT_RUN | 本地 Agent Activity 窗口的重新激活返回 `failed to activate captured window`；按 Computer Use 恢复规则停止进一步 UI 输入。Tauri Host 仍运行，临时 Provider 已到时限退出；没有截图级 PASS。 |

## 2026-10-29 阶段性 release checkpoint

**Given** 当前已跟踪源文件和 Agent Activity 的 Codex Desktop 本机回退，**When** 运行完整本地验证、release 构建并独立启动 Tauri host，**Then** 自动测试与真实 host 协议分开记录；用户要求的 Codex App 子目标在本次阶段提交后标记 `STALLED`，不把阻塞的 UI/持续 relay 宣称为完成。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `npm run check:local` | PASS | 退出码 0：28 项 Node UI、116 项 Rust workspace、154 项 Python tests；Rust fmt/check/Clippy、离线契约和 27 个 Provider Skill 引用通过。Node v22.23.4、npm 11.19.0、Rust 1.93.0、Python 3.11.4。|
| `npm run desktop:build` | PASS | 退出码 0；`target/release/wincraft-desktop.exe`，12,429,312 bytes，SHA-256 `6FE0BD26E1CD848CA8B28DBA41EF03EDE586DFE1B91D19C28A46DAE1A56A8093`。源码阶段提交 `a0366e1ecc9fb7e7eaaa1c23e14c161c400e56fd` 随后推送到 `origin/dev`。|
| 独立 release 启动与真实 Tauri host | PASS（协议） | 本次 EXE 独立启动；真实 `lease_probe.py` 经 host descriptor 连接后返回 `status=PASS`、退出码 0。descriptor 内容及路径未进入提交或证据。|
| 当前 GitHub Actions | PASS | run `40903194743` 在 Windows 上验证提交 `a0366e1` 的 `npm run check:local`，耗时 7m02s。workflow 不启动桌面窗口。|
| 当前 release 像素/Computer Use | NOT_RUN | 重新枚举后的管理器窗口激活失败；按 Computer Use 恢复规则不重试旧句柄或坐标。没有截图级 PASS。|
| Codex App 持续 connector relay 与 UUID 深链接 | STALLED / NOT_RUN | 一次真实授权快照已到 Provider，但持续 relay 未打通；本机状态回退不能提供权威运行状态。release UI 呈现和 `codex://threads/<UUID>` 点击/目标加载仍待验证。用户要求该子目标本次标记停滞。|

阶段提交与构建证明不替代托盘启动/退出、拖动、折叠、点击穿透救援、置顶、不同 DPI/显示器及真实 Codex App UI 验收；分项结果继续按 `PASS`/`FAIL`/`BLOCKED`/`NOT_RUN` 保留。

**2026-10-30 后续决定（取代上方当时的 `STALLED` 状态）：** 用户明确不需要和 Codex App 通信，也不需要启动 Claude Code；以本机进程状态判断在线，以数据目录提供会话详情。B08-02 已按 process + local-file 模型继续实现；当前 release 的可见呈现与 Codex UUID-only 导航仍待验收。

## 历史记录：2026-10-30 B08-03 按当时授权范围选择来源（后续已澄清）

**当时记录：** 用户随后明确要求 Codex App 与 Claude Code 通过本机进程和数据目录呈现，因此本节的“未查询 Codex App”仅描述该次 smoke 的选择，不再代表当前来源合同。

**Given** 该次 smoke 明确只选 Codex CLI 与 Claude Code，**When** Provider 使用 `--sources codex claude-code`，**Then** 只轮询这两个来源；这不证明当前 Codex App 本机文件适配已在 release 验收。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| 未选择来源的拒绝与未知来源校验 | PASS（单测） | 定向测试验证空列表、重复项及未知 source ID 均在启动 CLI 适配器前失败关闭。|
| `codex` + `claude-code` source selection | PASS（单测） | 43 项 live-source/overview 定向测试通过；未选 Codex App 时不调用 Desktop SQLite/rollout fallback，不保留上一轮 App 行，UI 标记“本轮未查询”。|
| B08-03-A1 Harness 入口/版本/未知边界矩阵 | PASS（文档与本机版本检查） | Codex CLI `0.138.0-alpha.7`、Claude Code `2.1.302`、OpenCode `1.1.14`、omp `15.5.7`；DSH 版本命令失败，保留未知。Codex CLI/Claude 有只读 smoke；Codex App 保持 STALLED，OpenCode/DSH/omp adapter 均 NOT_RUN，不把版本检查当作接入验收。|
| `npm run check:local` / CodeGraph / GitHub Actions | PASS | 本次工作树 28 项 Node UI、116 项 Rust workspace、159 项 Python 测试，契约与 27 个 Provider Skill 引用通过；CodeGraph 为 85 files、2,191 nodes、current。提交 `115cdc8` 的 GitHub Actions run [40914976329](https://github.com/exomind-team/WinCraft/actions/runs/40914976329) 在 Windows 上完整通过，耗时 7m59s。|
| 当前真实 Codex CLI / Claude 只读 adapter | PASS（本机只读） | 一次聚合快照显示 Codex CLI 来源 `online`、0 条可列会话；Claude `agents --json` 来源 `online`、2 条 `blocked` 后台 Agent。仅将来源健康和状态计数写入本机摘要，没有保存会话名称、项目、ID、输出或原始响应。|
| 当前 Tauri release global overview | PASS（协议/scene） | 当前 release 上以 `--sources codex claude-code` 运行实时只读 Provider：较早 60 秒 smoke 提交 4 次场景，最新 30 秒 smoke 提交 2 次；均退出 0 并走自身世界清理路径。Codex CLI 来源 `online`/0 条列表行，Claude 来源 `online`/2 条 `blocked` 后台 Agent；Codex App 标记 `not_requested` 且未读取。该 run 不提供像素截图或托盘验收。|
| 当前 release 像素验收 | NOT_RUN | Computer Use 窗口重新激活仍失败；不重试旧句柄/坐标，列表密度、真实点击和 DPI/多屏由人工按指南验收。|

## 2026-10-30 B08-02 本机进程与磁盘采集回归

**Given** Codex App 与 Claude Code 的本机进程状态和获准数据目录，**When** 两个来源合并成 Agent Activity 快照，**Then** 采集不启动目标 App/CLI，保留可读历史，遵守 256 条全局上限，并在裁剪时显示 `partial`。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `.venv\Scripts\python.exe -m py_compile examples\integrations\agent-board\live_sources.py tests\test_agent_live_sources.py` | PASS | Python 3.11.4，退出码 0。|
| `python -m unittest tests.test_agent_live_sources tests.test_agent_global_overview` | PASS | 40 项定向测试通过，退出码 0；新回归覆盖双来源超过上限、轮转保留及子 Agent 父链。|
| 初次 `scripts/local_harness_source_smoke.py` | FAIL（已修复） | 退出码 1；Codex App 128 条与 Claude Code 134 条合并后超出总览 256 条上限，导致整份快照失败。|
| 修复后本机 count-only smoke | PASS（本机只读） | `.venv\Scripts\python.exe scripts\local_harness_source_smoke.py` 退出码 0、耗时 0.3367 秒：Codex App 进程 `online` / 数据 `partial` / 128 条 / 2 条有界 Agent 输出；Claude Code 进程 `offline` / 数据 `partial` / 128 条 / 23 条有界 Agent 输出；两来源读取年龄均为 0 秒。无目标 Harness 启动，没有打印或持久化标题、ID、路径、prompt 或消息正文。|
| CodeGraph | PASS | `npm run codegraph:sync` 后 `npm run codegraph:status` 显示 91 files、2,469 nodes、current；count-only 结果另存于忽略的 `evidence/local/nextgen-2026-10-30/b08-02-local-process-disk-smoke.json`。|
| `npm run check:local` | PASS | 退出码 0：28 项 UI、116 项 Rust workspace、173 项 Python（1 项环境能力跳过），离线契约和 27 个 Provider Skill 引用检查通过。Node v22.23.4、npm 11.19.0、Rust/Cargo 1.93.0、Python 3.11.4。|
| GitHub Actions Windows CI | PASS | run [40999759040](https://github.com/exomind-team/WinCraft/actions/runs/40999759040) 验证提交 `aae58b4` 的 `npm run check:local`，全步骤成功，耗时 11 分 40 秒。|
| `npm run desktop:build` | PASS（重试） | 首次退出码 1，已有同仓 release 进程占用 EXE；按既有授权停止该进程后重建成功，退出码 0。产物 `<repo>\target\release\wincraft-desktop.exe`，13,279,232 bytes，SHA-256 `C7371C98B747A58D3F5F9FB8B9967B12BBBF66D797B3C89DFE3E9B1578BDEE90`。|
| 独立 release 启动 `--open-manager` | PARTIAL | 新 release 进程启动，`窗构 · 世界管理器` 被窗口枚举器发现；Computer Use 初次及一次重新枚举恢复均报 `failed to activate captured window`，未取得截图，像素/交互验收为 `NOT_RUN`。|
| 当前 release 可见呈现与 UUID 深链接 | NOT_RUN | 上述 smoke 只证明本机采集与合并；不证明 Tauri release 像素、原生点击或目标会话加载。|

多来源裁剪按来源等额分配初始预算，依 `source_sequence` 选择较新的叶会话，并把被选中子 Agent 的父链一并保留；最终不足额可用时再扩展预算。被裁剪来源的可读数据健康改为 `partial`。TeamSense 本机用量/额度收集仅作为后续额度 HUD 的来源研究；WinCraft 不读取其 `auth.json` 或供应商凭据，待 TeamSense 提供经授权的本机脱敏只读汇总后再实现 Codex、MiniMax、DeepSeek 卡片。

## 2026-10-30 B04-03 resumed candidate and real-host probe

**Given** the manager shortcut implementation landed after the previous `target/release` executable was built, **When** resume the Windows host work, **Then** distinguish the stale executable from the current candidate, validate the latter against the actual Tauri/Rust server, and keep native key delivery separate from protocol success.

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Earlier `target/release` process | 已停止（旧构建） | Running EXE SHA-256 `5E6061827A3B4527BFEEA1307A5945A8EAB8976C8BDC47A86BFE2F4B654B6F8F`，文件时间 2026-10-30 15:29；快捷键功能提交 `4bc3e81` 时间为 15:50，因此该进程早于功能实现，不能验证新管理器快捷键控件。|
| 隔离候选 `target/stage-309af17/release/wincraft-desktop.exe` | PASS（已测试，现已停止） | 文件 13,559,808 bytes，SHA-256 `6840654D6DBEFB780B758618805B241AC96D22D57B8E7F4D49B102DFA3E58E10`；真实 Tauri-hosted `lease_probe.py` 41 项通过。|
| 标准 release `target/release/wincraft-desktop.exe` | PASS（2026-10-30 时运行，后已替换） | `npm run desktop:build` 退出码 0；13,559,808 bytes，SHA-256 `C949FC2359B5D36DA9FF3C2CAD395D07914699D13DF9130A985CC3160070BA25`。当时以 `--open-manager` 启动为唯一 WinCraft 进程；同一标准路径产物上的真实 Tauri-hosted `lease_probe.py` 41 项通过。2026-10-31 已停止该进程并替换为当前 release。|
| 新候选上的真实 Tauri-hosted `lease_probe.py` | PASS | 退出码 0，共 41 项：授权/协议拒绝、动态 insert/move/replace/props/remove、租约过期、旧 epoch fencing、断线重连、慢消费者断开，以及原生窗口属性报告。探针只创建并清理自己的合成世界；runtime descriptor 路径与 token 未写入证据。|
| 当前 OS 全局快捷键注册/触发/撤销/IME | NOT_RUN | Computer Use JS 报告原生管道不可用（系统找不到指定的文件）。当前候选没有输入或启用任何组合键；B04-03-A1/A2/A3 仍 `PARTIAL`，不得将旧进程无控件或协议 probe 当作快捷键失败/成功。|
| Provider Skill 收集规则回归 | PASS | `python skills/wincraft-provider/scripts/verify.py` 退出码 0；检查过程/本机文件数据路径，并拒绝旧的 App relay 或 Claude CLI 查询说明。|
| `npm run check:local` | PASS | 退出码 0：Node 28 项；Rust workspace 全部测试、fmt/check/Clippy 通过；Python 174 项通过，1 项因 Windows symlink 能力跳过。环境：Node v22.23.4、npm 11.19.0、Rust/Cargo 1.93.0、Python 3.11.4。|
| GitHub Actions run `41022563172` on `4bc3e81` | FAIL（Clippy） | `npm run check:local` 走到 Rust Clippy 后失败：Rust 1.99 `clippy::collapsible_match` 要求将 `if code.is_none()` 折进 `RunEvent::ExitRequested` match guard。没有单测或构建失败。|
| 后续 GitHub Actions `41024348330` (`309af17`) 与 `41026654580` (`c36e4af`) | PASS | 同一源码使用 match guard 后，两次 Windows Actions 均通过；当前本地 HEAD 对应 run `41026654580`。本地未提交改动不包含在该远端 run 中。|
| CodeGraph | PASS | `npm run codegraph:sync` 同步 1 个 Python 文件；`npm run codegraph:status` 为 current，91 files / 2,501 nodes。|
| 标准路径 EXE + 中文验收 ZIP | PASS | `evidence/local/WinCraft-0.1.0-alpha.1-standard-20261030-c36e4af-three-source.zip` SHA-256 `B90D044F20D1727508BFE26FA6AB2C73CA7E0CC245C527C15AA0EDC933B1E886`；包内 EXE SHA 与上方标准 `target/release` 构建一致，`SHA256SUMS.txt` 对 EXE 和两份验收文档逐项通过；不含 runtime descriptor。|

本轮将新候选留在前台供后续本机验收；热键授权、真实按键、跨进程冲突、注销后不残留和 IME 输入保护仍需 Computer Use 恢复后验收。对应机器本地摘要在忽略的 `evidence/local/nextgen-2026-10-30/b04-03-runtime-resume-20261030.json`；不含 runtime descriptor 或 bearer token。

GitHub Actions 复盘：run [41022563172](https://github.com/exomind-team/WinCraft/actions/runs/41022563172) 在 Windows 的 `npm run check:local` 失败；Rust 1.99 Clippy 将 `RunEvent::ExitRequested` 分支中的嵌套 `if code.is_none()` 升为 `clippy::collapsible_match` 错误。修复是将条件移入 match guard，已在 commit `309af176` 核实；后续 run [41024348330](https://github.com/exomind-team/WinCraft/actions/runs/41024348330) 与当前 HEAD 的 run [41026654580](https://github.com/exomind-team/WinCraft/actions/runs/41026654580) 均通过。当前本机 Rust 1.93 的 `npm run check:local` 通过；远端 Actions 仍以 Rust stable 版本为准。

## 2026-10-30 B08-02 本机数据来源复核

**Given** 用户指定 Codex App 与 Claude Code 只从本机进程状态和固定数据目录采集，**When** 重跑 count-only 来源 smoke，**Then** 只报告进程状态、数据质量、新鲜度和有界计数，不启动 Harness、不连接 WinCraft Host、不输出会话内容。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python scripts/local_harness_source_smoke.py` | PASS（本机只读） | Python 3.11.4，退出码 0，0.5303 秒；Codex App `online` / 数据 `partial` / 128 条 / 2 条有界输出 / age 0 秒；Claude Code `offline` / 数据 `partial` / 128 条 / 24 条有界输出 / age 0 秒。两来源合计 256 条，未启动目标进程。|
| 数据保留边界 | PASS | smoke 明确报告 `session_values_persisted_or_printed=false`；本机 evidence 只保存状态、计数和耗时，不保存标题、项目名、session ID、prompt、消息正文或 descriptor。|
| 标准 release `live_provider.py` | PASS（来源→Host 协议/scene） | 12 秒真实 Tauri Host run，退出码 0；仅选择 `codex-app` 与 `claude-code`，提交 3 次快照：Codex App `online`/128 行，Claude Code `offline`/128 行，Codex CLI `not_requested`；Provider 明确确认清理自己的临时 world。原始 Provider 输出未保存。|
| 标准 release 三来源 `live_provider.py` | PASS（来源→Host 协议/scene） | 12 秒真实 Tauri Host run，退出码 0；选择 `codex`、`codex-app`、`claude-code`，提交 3 次快照：Codex CLI `online`/0 行、Codex App `online`/128 行、Claude Code `offline`/128 行。Codex CLI 走固定 `useStateDbOnly=true` app-server；Codex App/Claude 由进程 + 本机文件读取。Provider 确认清理自己的临时 world；Codex 进程数量测试前后同为 2。原始 Provider 输出未保存。|
| Codex App 进程文案修复后 live smoke | PASS | 标准 release 上重新提交 2 次 Codex App/Claude 快照：App `online`、Claude `offline`，临时 world 清理确认。scene 标签现使用进程状态用语，没有“已桥接/等待 Agent 桥接”。|
| `test_live_scene_separates_health_data_quality_and_freshness_for_all_sources` | PASS | 实时 scene schema 回归确认三源健康/freshness 分离、App/Claude 数据质量徽标独立；Codex App online/offline/unavailable 文案对应进程状态，不再声称“桥接”。|
| `test_codex_app_preview_binds_name_status_project_output_and_uuid_link` | PASS（合成） | scene schema 回归检查标题、状态、项目、最近 Agent 输出，及仅在 Host capability 打开时的 UUID-only 原生动作；不读取真实会话。|
| `npm run check:python` | PASS | 退出码 0；Python 176 项通过，1 项 Windows symlink 能力跳过；`skills/wincraft-provider/scripts/verify.py` 通过。|
| `npm run check:local` | PASS | 加入上述 scene 回归和 Codex App 进程文案修复后重新执行；UI 28 项、Rust workspace 141 项、Python 176 项通过，1 项 Windows symlink 用例因环境能力跳过；fmt/check/Clippy、离线契约和 Skill 校验均通过。|
| release UI 与三来源呈现 | NOT_RUN | live provider 证明同一 standard Host 接受了三源 scene 更新，不证明窗口像素、卡片内容、freshness/unknown 控件或 UUID-only 深链。B08-02-A1 的 L2 scene 场景已 PASS；A4 仍按用户要求 STALLED，A5 的视觉新鲜度提示仍 PARTIAL。|

count-only 结果记录在忽略的 `evidence/local/nextgen-2026-10-30/b08-02-local-process-disk-smoke-resume-20261030.json`；两源与三源标准 release Provider 摘要分别记录在 `b08-02-standard-release-live-provider-smoke-20261030-current.json` 与 `b08-02-standard-release-three-source-smoke-20261030.json`；进程文案修复后复核在 `b08-02-standard-release-process-label-recheck-20261030.json`。三源 L2 场景通过：同一 Provider world 收到 Codex CLI、Codex App 和 Claude Code 的状态/记录并提交到 Host。scene freshness/data-health 与 Codex App 卡片字段回归记录在 `b08-02-three-source-scene-test-20261030.json`。Host 只持有可重建的 scene/会话状态，Provider 清理后临时 world 已销毁；本证据没有保存标题、项目名、session ID、prompt 或消息正文。截图、卡片像素、freshness 展示和 UUID 深链继续保持各自验收状态。

## 2026-10-30 B04-04 TouchAI read-only source review

**Given** 用户指定 TouchAI 本地仓库用于学习，**When** 只读检查其固定 commit、许可证和召回/输入/取消源码，**Then** 更新 WinCraft 窄用例差异矩阵，不启动 TouchAI、不读写其数据库、不复制 GPL 源码。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| TouchAI source identity | PASS（只读） | 指定本地 checkout 为 `main`、HEAD `cdc9b399d0ea6813be321b6a87e39d3532d1a7da`、工作树 clean。运行栈为 Tauri 2 + Vue 3，`@touchai/desktop` 1.2.2。|
| license and permission boundary | PASS（静态核对） | `COPYING` / manifest 声明 GPL-3.0-or-later；TouchAI 产品规则要求数据库 schema 变更显式批准，AgentService/对话运行时为 RFC-first 高风险区。WinCraft 未复制源码、未修改仓库。|
| 实际召回/输入/结果/取消路径 | PASS（源码阅读，非运行） | `Alt+Space` -> SearchView 恢复焦点/模型 -> SearchRequest 传 text/attachments/input snapshot/model/provider -> `sessionTaskCenter.startTask`；启动可 AbortController，运行中 `cancelTask`。TouchAI 内部有流式 AgentService；没有发现稳定的外部 WinCraft bridge/API。|
| B04-04-A1 live workflow | NOT_RUN / BLOCKED | 本轮仅授权学习源码，未启动 TouchAI、未打开会话、未请求模型或读写数据库；没有已定义的外部 Provider contract。因此没有宣称已复现真实 workflow。|
| B04-04-A2/A3 | PASS（差异与许可边界） | 矩阵将 stream/context/MCP/tool execution 列为未接入/来源自有；未将其标成等价，也未将 GPL-3.0-or-later 代码复制到 WinCraft。|

细节与来源路径见 [`docs/integrations/touchai-gap-matrix.md`](../integrations/touchai-gap-matrix.md)；本机摘要在忽略的 `evidence/local/nextgen-2026-10-30/b04-04-touchai-readonly-source-review.json`，不含 TouchAI 用户数据或凭据。B04-04 仍为 `BLOCKED`，等待明确的 live workflow/adapter contract 授权；可继续独立的其他交接任务。

## 2026-10-30 B05-02 TeamSense model-quota Provider

**Given** TeamSense 提供授权的缓存只读汇总，**When** WinCraft 收到 DeepSeek/MiniMax 数据，**Then** 各币种、模型与周期分别呈现，明确显示缓存 freshness 和 API 连接状态；缺少字段、Codex 不在接口或账户标识缺失时保持未知，不推算余额。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| TeamSense route/auth source review | PASS（L1，静态） | `docs/agent-api.md` 和 `worker/app.ts`/`worker/routes/agent-api.ts` 确认 `GET /v1/integrations/models` 经 `requireApiToken`，仅 `data:read` scope；返回缓存的 DeepSeek/MiniMax/Sub2API 和 freshness。它不列出 Codex；`/api/codex/quota-history` 是管理员保护的同源接口，不属于 `data:read` Agent API。`GET /v1/dashboard` 虽含 `modelQuotas`，也返回财务、项目和服务摘要，且该 quota projection 不提供账户/周期身份，因此 Provider 不请求它。未读取 credentials、数据库或业务快照。|
| TeamSense Codex quota collector source review (`e63bbe5`) | PASS（L1，静态） | 独立 quota collector 可选读取本机 `auth.json` 的 access token/account ID，在内存中请求固定的 `chatgpt.com/backend-api/wham/usage`；默认 `quota_query_enabled=false`，上传目标另有 quota disclosure。成功结果绑定请求时账号并核对请求期间是否切号，再作为签名 collector report 上传；访问 token 不进入报告。此路径与 rollout/state SQLite 活动采集分开，WinCraft 没有复用它，也未读取凭据或发起上游请求。|
| `python -m unittest discover -s tests -p test_team_sense_quota.py -v` | PASS | 11 个合成行为用例：币种/模型/周期隔离、零值与缺失区分、断线保留脱敏 last-good projection、freshness 与 API 健康分离、Codex unknown、过滤账户/管理字段、固定 GET/禁止重定向与 TLS URL 约束、额度状态冲突、模型截断披露及声明式进度条场景。未访问 TeamSense 网络。|
| `npm run check:local` | PASS | 退出码 0：Node UI 28 项、Rust workspace 141 项、Python 187 项（1 项 Windows symlink 能力跳过）；离线契约、fmt/check/Clippy 与 Provider Skill 30 项引用校验通过。环境：Windows 11 Pro build 22000、Node 22.23.4、npm 11.19.0、Rust/Cargo 1.93.0、Python 3.11.4。|
| 标准 release Tauri Host + `provider.py --demo --duration-seconds 8` | PASS（L2 scene/protocol） | 运行中的 `wincraft-desktop.exe`（PID 69936）接受合成 Provider 的 world/scene；Host 返回普通组件 capability，Provider 确认清理自己的临时世界。runtime descriptor 路径和 bearer token 未写入终端记录或证据。未取得窗口截图，像素/可读性 NOT_RUN。|
| TeamSense live API | NOT_RUN | 本轮没有 TeamSense API token，也没有发起远端请求；没有修改 TeamSense。真实 freshness/cache 样本、账户归属、断线恢复需配置经授权的 `data:read` token 后验证。|
| B05-02-A1/A2/A3 | PARTIAL / PARTIAL / PASS（源码与合成） | A1 的 provider/window/currency 不混算已由合成数据检查，但 endpoint 不提供 account ID，账户归属留缺口；A2 freshness/API 断线 scene 已通过合成测试和 Host scene 接受，未做真实像素验收；A3 只使用已定位的固定只读 GET 和 `--demo`，没有修改 TeamSense。B05-02 保持 `IMPLEMENTED_UNVERIFIED`。|

实现入口为 [`examples/integrations/model_quota/`](../../examples/integrations/model_quota/)；忽略的本机摘要为 `evidence/local/nextgen-2026-10-30/b05-02-team-sense-quota-provider.json`。Codex quota、TeamSense 账户身份及真实服务 freshness 仍是下一步边界。

## 2026-10-30 B08-03-A2 standard Tauri Host scope concurrency

**Given** one current Tauri Host and a scoped parent world, **When** two authenticated preview writer sessions and a read observer operate concurrently, **Then** each writer changes only its disjoint subtree, readers receive filtered snapshots, and the probe destroys only its own temporary world.

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `examples/python/scope_probe.py` against standard release Host | PASS（L2 protocol; synthetic sources） | 退出码 0。两个独立 WebSocket writer session 在 `focus`/`tasks` scopes 更新不同 revision；读者只收到授权 scope；结构 patch、typed slot CAS/grants/revocation、parent revocation、稳定 0.3 refusal 均通过，探针确认自身世界已销毁。Host PID 69936，EXE SHA-256 `C949FC2359B5D36DA9FF3C2CAD395D07914699D13DF9130A985CC3160070BA25`；descriptor 路径、token、world ID 未保存。|
| B08-03-A2 判定 | PARTIAL | 已证明真实标准 Host 的两个独立 writer sessions 并发且彼此隔离；值与身份为合成数据，并由同一探针进程编排，尚未证明 Codex/Claude 真实来源作为独立 provider 运行。|
| UI / source adapter | NOT_RUN | 本次不涉及窗口像素或真实 Harness 业务读取；Computer Use 原生管道仍不可用。|

忽略的本机摘要：`evidence/local/nextgen-2026-10-30/b08-03-standard-tauri-scope-probe.json`。

## 2026-10-31 B08-03-A3 组件动作所有权路由

**Given** 一个由世界 authority 划分、且含两个组件 scope 的合成世界；**When** 用户触发 scope 内按钮；**Then** 事件只发送给该组件 scope 的当前写者，动作回执必须由同一 writer 的当前租约提交。未归属布局、旧/异 scope writer 与稳定 0.3 客户端均不能接管该动作；scope 原生窗口动作保持不支持。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo test -p wincraft-server scoped_interaction --no-fail-fast` | PASS（3 tests） | Hub 回归确认事件只路由给组件 owner、异 scope writer 不能回执、删除 scope 会 fence 旧 writer 并结束 pending action；loopback WebSocket 回归确认 `scope.interaction`/`scope.action.result` 的 lease 绑定，并确认 stable 0.3 不宣告 component leases 且调用 preview method 得到 `PROTOCOL_MISMATCH`。未归属布局和 `native_window_action` 被拒绝。|
| Python SDK、preview schema 与 demo 定向回归 | PASS（37 tests） | `tests.test_client_capabilities`、`tests.test_client_event_queue`、`tests.test_scope_preview_contract`、`tests.test_scope_interaction_demo` 全部通过；SDK 在 capability 不存在/版本或形状不匹配时失败关闭。|
| `npm run check:local` | PASS（完整本地门禁） | UI 28、Rust workspace 144、Python 193（1 项 Windows symlink 能力跳过）、离线契约与 Provider Skill 31 个引用通过；fmt、check、Clippy 均通过。第一次完整门禁暴露 `record_pending_action` 8 参数 Clippy 失败，随后用具名 `PendingAction` 输入结构收敛参数并重跑通过。|
| `npm run desktop:build` + release Provider smoke | PASS（build / L2 create-and-cleanup） | 产物为 `target/release/wincraft-desktop.exe`，13,572,608 bytes，SHA-256 `0E5ECCAD24E04653C3E8F878CF96C370E3A74F68AC4EFE742C70EA10284422C7`。新 release 以 `--open-manager` 启动；`scope_interaction_demo.py --duration-seconds 1` 成功协商 preview capability、创建/划分 scope、取得 scope writer 并清理自己的临时世界，退出码 0。该短 smoke 没有点击按钮，也不证明动作已在屏幕中触发。|
| B08-03-A3 判定 | PARTIAL（L1-L2） | 协议、Host 路由、scope lease 回执与 stable 0.3 隔离已由测试覆盖。原生窗口中的真实点击/动作回执，以及 Codex/Claude 两个真实来源的独立 Provider 仍未验收。|
| 原生点击 / 像素 | NOT_RUN | 本轮没有可用的 Computer Use 输入管道；没有将 WebSocket/fixture 结果冒充原生 UI 验收。|

运行环境：Windows 11 Pro build 22000；Node `v22.23.4`、npm `11.19.0`、Python `3.11.4`、Cargo/Rust `1.93.0`。本机脱敏测试摘要（Git 忽略）：`evidence/local/nextgen-2026-10-31/b08-03-a3-scoped-interaction-tests.json`。不记录 descriptor、bearer token、world/session UUID 或真实业务数据。

## 2026-10-31 B08-02-A5 本机来源 freshness recheck

**Given** 用户已授权的本机 Codex CLI、Codex App 与 Claude Code 来源；**When** 当前 release 的只读 Provider 每 5 秒读取进程元数据和有界本地快照，共运行 11 秒；**Then** 三轮汇总显示来源在线状态与逐会话状态分开，未知状态继续显示 `unknown`，Provider 自行清理临时世界。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `live_provider.py --sources codex codex-app claude-code --duration-seconds 11 --refresh-seconds 5` | PASS（L2 source-to-Host protocol） | 退出码 0；当前标准 Tauri Host SHA-256 `0E5ECCAD24E04653C3E8F878CF96C370E3A74F68AC4EFE742C70EA10284422C7` 接收 3 次快照并确认自身世界清理。汇总状态三轮一致：Codex CLI online/0 个可列状态；Codex App online/128 条状态未知；Claude Code offline/128 条历史状态未知。没有启动任何 Harness 进程；会话名称、项目、ID、输出与原始记录未写入终端摘要或证据。|
| `python scripts/local_harness_source_smoke.py` | PASS（L2 本机文件来源） | 退出码 0；Codex App 进程在线、Claude Code 进程离线；两来源的磁盘读取均标为 partial，读取年龄为 0 秒；没有逐会话权威状态时保留 `unknown`。脚本只打印来源健康、读取年龄和聚合计数；没有启动 Harness，也没有打印或持久化会话值。|
| 当前 release headless Host + `live_provider.py --sources codex-app claude-code --duration-seconds 12 --refresh-seconds 5` | PASS（L2 source-to-Host） | Provider 接收 3 次真实本机来源快照、退出码 0，并确认 `world.destroy` 成功。Codex App 在线、Claude Code 离线，逐会话状态维持 `unknown`；Host 在测试后由 runner 终止，未把这次运行计作 Host graceful shutdown 或原生 UI 验收。忽略的本机汇总只保留来源健康与状态计数。|
| B08-02-A5 判定 | PARTIAL | 本机来源确实更新，来源在线状态、磁盘可读性与逐会话 `unknown` 分开；刷新时间也在数据投影中。freshness 标签的窗口像素/时效提示仍未通过原生 UI 观察。|
| Codex App 深链与 UI | STALLED / NOT_RUN | Computer Use 原生管道重试仍不可用；本次没有触发 Codex thread 导航，也没有用其他自动化代替 UI 验收。|

忽略的本机汇总证据：`evidence/local/nextgen-2026-10-31/b08-02-a5-live-source-snapshot.json`、`evidence/local/nextgen-2026-10-31/b08-02-live-local-source-smoke-20261031/summary.json` 与 `source-only-summary.json`。其中不含 descriptor/token、会话身份或正文。

## 2026-10-31 B08-03-A4/A5 验收状态复核

**Given** 用户已打开 Claude Code 的某条会话详情；**When** 在 Codex 来源与 Claude 来源之间切换、再切回，并且该快照暂时不再包含原会话；**Then** 总览恢复该来源自己的详情身份与页码，保留最后已知身份和最新来源新鲜度，明确显示撤销状态未知；记录回来后恢复实时详情。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest tests.test_agent_global_overview -v` | PASS（16 tests） | 覆盖 Codex/Claude/Codex App 导航与详情字段、每来源保存详情、跨来源往返恢复、缺失 tombstone、新鲜度与 unknown 撤销状态、过期 detail 拒绝和分页。|
| `npm run check:local` 当前工作树 | PASS | 退出码 0：Node UI 28 项、Rust workspace 145 项、Python 205 项（1 项因 Windows symlink 创建能力不可用而跳过）；Rust fmt/check/test/Clippy、离线契约与 33 个 Provider Skill 引用检查通过。环境：Windows 11 专业版 build 22000、Node 22.23.4、npm 11.19.0、Rust/Cargo 1.93.0、Python 3.11.4。|
| Provider 视图提交 [`0696cbeb`](https://github.com/exomind-team/WinCraft/commit/0696cbeb9b3ef69cb9c6a9b43901fae6e922ea7b) / Actions [41128511607](https://github.com/exomind-team/WinCraft/actions/runs/41128511607) | PASS | 15 项总览测试含跨来源详情身份/page 与 tombstone 往返回归；Windows full local gate 通过（12m58s）。该提交只改仓库中的独立 Python Provider，不改 Tauri/Rust EXE。|
| 当前标准 release + `global_overview_provider.py --duration-seconds 5` | PASS（L2 scene/cleanup） | 当前 Tauri Host 接受仓库合成总览场景；Provider 5 秒后退出并确认仅清理自己的临时世界。该 smoke 不含真实会话数据，也不提供新截图。|
| B08-03-A4 判定 | PARTIAL | 新回归证明 Codex、Codex App、Claude Code 的来源切换可恢复各自 selected detail；如果快照不再包含该会话，则跨来源离开/返回仍保留显示身份与来源 freshness，明确标为撤销未知，记录恢复后回到实时详情。来源文件没有逐会话权威撤销信号，所以不伪判为 revoked；最新 build 的 source-switch/tombstone 像素仍 NOT_RUN。|
| B08-03-A5 判定 | PASS（L1-L4） | 首屏 Codex 并行量与 Claude 状态预览由 16 项总览测试覆盖；A7 release 截图已记录 Overview `520×421`、Claude list `520×422`、Codex list `520×512`、detail `520×477`，并验证动作回执和受限窗口高度。当前 release synthetic scene/cleanup smoke 通过。|

忽略的本机汇总证据：`evidence/local/nextgen-2026-10-31/b08-03-a4-missing-selection-retest.json`、`evidence/local/nextgen-2026-10-31/b08-03-a4-a5-overview-recheck.json` 与 `evidence/local/nextgen-2026-10-31/b08-03-a4-source-switch-regression.json`。Host `scope.status` 描述的是 WinCraft component scope，不代表 Codex/Claude 会话撤销；A4 保持 PARTIAL，等待来源提供逐会话撤销权威事实与当前 build 原生 UI 验收。

## 2026-10-31 B06-04 合成配置包再验

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `tools/pack/export_pack.py` | PASS | 退出码 0；新导出 `workday-synthetic-20261031-2.wcp`，1,109 bytes，SHA-256 `3407ec6895809a6227860e6e83e952dcc3df31b083123c5e8fd6171e8527a840`。归档只有 `pack.json` 与声明的 `blueprints/workday.json`；`adapter` 为 null。|
| 合成归档隐私/内容扫描 | PASS（L0-L1） | 未发现凭据字段、绝对用户路径、runtime/session 标记或未声明归档条目。仅检查仓库合成 fixture，不代表用户自定义包都自动脱敏。|
| `python -m unittest tests.test_pack_export -v` | PASS（10 passed / 1 skipped） | 覆盖确定性导出、只打包声明文件、拒绝覆盖、拒绝 adapter/provider 二进制与描述文件、大小/路径/schema 限制、不会接触 Host 或执行 adapter。1 项 symlink 用例因 Windows 当前无法创建 symlink 而跳过。|
| B06-04-A2 判定 | PARTIAL | 本次合成包静态卫生通过；第二个独立用户/设备导入相同包仍 NOT_RUN。A1 clean-install 不自动下载/执行 Provider 与 A3 缺失区域管理器可见解释也仍需独立环境/原生 UI 验收。|

忽略的本机证据：`evidence/local/nextgen-2026-10-31/b06-04-synthetic-export-audit.json` 与归档 `workday-synthetic-20261031-2.wcp`。

## 2026-10-31 本机试用入口、Obsidian Workspace 与 Provider bundle

**Given** 用户使用管理器复制 runtime descriptor、拖入 WCP 并选择启用本机数据来源；**When** descriptor copy、WCP preview/install/launch、Obsidian 元数据和额度来源选择运行；**Then** 管理器只允许本机用户在最后确认后运行代码包；Obsidian 投影只含插件生成的本机元数据；未选额度来源不占位显示。

| 检查 | 状态 | 实际结果与边界 |
|---|---|---|
| `npm run check:local` | PASS | UI 30 tests；Rust 155 tests passed、1 个依赖本地产物的定向 test ignored；Python 238 tests passed、1 个 Windows symlink 能力用例 skipped；离线契约、严格构建与 Clippy 通过。|
| `scripts/browser_smoke.py` | PASS（浏览器 DOM，不是原生） | 使用本机 Chromium-compatible Edge 与当前构建 TypeScript 模块，28 项合成 DOM 检查通过，包含动态组件、折叠/展开、滚动条、文本溢出、主题和 Obsidian Workspace 动作。新结果在 ignored local evidence；`evidence/assistant-run/` 原始文件已恢复原样。|
| Provider bundle parser | PASS | 拒绝路径穿越、Windows 保留路径、超大 manifest、runtime/extension 不匹配、预览后归档变化、已安装入口篡改和同版本覆盖。预览/解包本身不会执行入口。|
| `python scripts/build_provider_bundle.py` + Host parser | PASS | 构建忽略目录中的合成 `.wcp`，Rust Host parser 成功预览 manifest、Python 入口、文件上限与摘要；包不含 runtime descriptor 或业务数据。|
| Manager launch gate | PASS（unit） | 模拟 provider launcher 验证：未请求确认时启动次数为 0；第一次操作只打开确认；第二次明确确认才启动。真实 Manager 点击与 child 进程退出状态仍待原生 UI 验收。|
| `scripts/model_quota_headless_smoke.py` | PASS | 真实 release headless Rust Host + 合成 Codex rollout；不读真实凭据、不联网；Provider exit 0 并确认自己的 world 已清理，随后按 smoke 策略强制停止 Host；临时文件删除。|
| `npm run desktop:build` | PASS | exit 0；生成 `target/release/wincraft-desktop.exe`，14,209,536 bytes，SHA-256 `E8F949E73C0A4BD0182B26D327162599F133658A244B4B498E1DF9978C447B76`。当前 Host 用 `--open-manager` 独立启动，供用户手工验收。|
| 合成 `.wcp` 用户拖放/安装/运行 | NOT_RUN | 代码包解析与安装单元测试通过；本轮未用 Computer Use 对 Manager 进行原生拖放/按钮点击。|
| Obsidian Workspace 插件与原生数据流 | NOT_RUN | 通用插件 ZIP 和 Provider 已构建；没有将插件安装到用户 Vault，也没有把任何 Vault 数据读入验证。插件多窗口计数只覆盖启用本插件的实例。|
| 管理器 descriptor copy | PARTIAL | Rust 命令仅允许 exact internal Manager world 并从 Host descriptor guard 读取路径；授权单测通过。系统剪贴板真实写入未通过原生 UI 点击验收。|
| 本机图形化额度来源配置 | PARTIAL | 选择/增删、API Key 不落盘与长时间配置窗口 ACK 栅栏有 Python 回归；Tk 来源选择器未在真实桌面内操作，真实账户/网络读取均未执行。|

本机 `target/` 中同时生成 `target/provider-bundles/wincraft-sample-provider.wcp` 与 `target/obsidian-plugin/wincraft-workspace-dashboard.zip`；这两个构建产物未纳入 Git。真实 Obsidian、深色主题/视觉体验、窗口拖放、系统剪贴板与 provider live launch 均应由用户手工验收后再标 PASS。原始 `evidence/assistant-run/` 未修改，逐机日志仍留在忽略的 `evidence/local/`。

## 2026-10-31 B06-03 Host 行为回归复跑

**Given** 一个含既有世界的 Host、经授权的合成 Provider inventory 和配置 blueprint；**When** 计划 generation 变化、用户取消、显式授权后重新预览、应用中途失败或用户执行回退；**Then** 旧计划失效、既有世界不被清空，Host 报告部分成功/清理结果，并且只删除仍与导入账本完全一致的资源。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo test -p wincraft-server pack_import --no-fail-fast` | PASS（16 tests） | 覆盖 generation invalidation、取消不创建资源、权限需独立 host grant 后 re-preview、只为选中 Provider 分配写入、部分失败报告与 ledger-guarded rollback；退出码 0。|
| 当前 release Manager UI | NOT_RUN | 当前 release SHA-256 `0E5ECCAD24E04653C3E8F878CF96C370E3A74F68AC4EFE742C70EA10284422C7` 已启动；Computer Use native pipe 不可用，预览/授权重规划/应用/取消/回退点击与画面仍未验收。|
| B06-03-A1/A2/A3 判定 | PARTIAL / PARTIAL / PARTIAL | Rust Host 行为回归已复跑；不将单测或无界面 Host 请求记作 manager 的人工预览、回退 UI 通过。|

忽略的本机回归摘要：`evidence/local/nextgen-2026-10-31/b06-03-pack-import-regression.json`。

## 2026-10-31 B08-03-A2 两个真实来源独立 Provider

**Given** 当前 Windows Tauri release；**When** 本机只读 Provider 分别为 Codex CLI 与 Claude Code 启动两个独立 OS 进程，加入同一父世界的不同 scope 并写入只读呈现投影；**Then** 两个 scope 写租约在同一时间窗口内并存、各自 revision 前进，进程离线不伪造逐会话状态，父 Provider 清理其自己的临时世界。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python examples/integrations/agent-board/scoped_live_sources.py --runtime <matched-local-descriptor> --duration-seconds 20` 对当前 Tauri release | PASS（L2；真实本机来源） | 当前 Tauri release SHA-256 `0E5ECCAD24E04653C3E8F878CF96C370E3A74F68AC4EFE742C70EA10284422C7`；退出码 0。两个不同 OS Python Provider 进程分别完成 scope 写入，程序内部验证 PID 不同；scope revision 均到 3，两个写租约重叠 19.91 秒。Codex CLI online/0 条可列状态；Claude Code offline/138 条本机历史状态未知。来源摘要没有会话标题、项目、ID、Agent 输出、PID 或 runtime descriptor；没有启动 Codex App 或 Claude Code 进程。|
| `npm run check:local` 当前工作树 | PASS | 退出码 0：Node UI 28 项、Rust workspace 144 项、Python 197 项（1 项因 Windows symlink 创建能力不可用而跳过）；Rust fmt/check/test/Clippy、离线契约与 33 个 Provider Skill 引用检查通过。环境：Windows 11 专业版 build 22000、Node 22.23.4、npm 11.19.0、Rust/Cargo 1.93.0、Python 3.11.4。|
| 世界与子进程清理 | PASS | authority Provider 确认销毁其临时世界；进程检查确认没有残留 `scoped_live_sources.py --source-worker` worker。|
| B08-03-A2 判定 | PASS at L2 | 已验证两种真实来源、两个独立 Provider 进程在一个 Tauri Host 同时持有不相交 scope writer 并实际更新各自 namespace。像素和点击验收仍由 A3/A7 跟踪。|

忽略的脱敏汇总证据：`evidence/local/nextgen-2026-10-31/b08-03-a2-independent-source-writers-recheck.json`。

## 2026-10-31 B08-03-A4 metadata-only scope lifecycle signal

**Given** 一个仍有效的 0.4-preview.1 parent authority、一个 lifecycle scope 和两个分离的本地来源 scope；**When** 两个 Provider 各自写入并断线，parent 删除 Codex scope 根；**Then** Host 分别返回 `online`、`stale`、`revoked`，Claude Code sibling 仍为 `stale`，且只向 parent 暴露 generation/revision/sequence/status 元数据。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo fmt --all -- --check` | PASS | 退出码 0。|
| `cargo test -p wincraft-core parent_reads_metadata_only_scope_lifecycle_without_sibling_data -- --nocapture` | PASS | 1/1 通过；覆盖 trusted local operator 读取、active authority 过期后成员仍可读自己的 scope但不能读 sibling、future generation `unknown`、撤销 tombstone、无 business data/Writer identity。|
| `cargo test -p wincraft-server preview_websocket_scopes_allow_disjoint_writers_and_filter_readers -- --nocapture` | PASS | 1/1 通过，真实 loopback Rust Host WebSocket；覆盖能力声明、metadata-only status、权限隔离、撤销与旧协议拒绝。|
| `python -m unittest tests.test_agent_scoped_sources tests.test_client_capabilities tests.test_scope_preview_contract -v` | PASS | 37/37 通过；Python 校验精确字段白名单、请求身份、generation 和 metadata 类型。|
| `python scripts/check_contracts.py` | PASS | 退出码 0；请求/响应 schema、正反 fixture 与本地协议检查通过。|
| `npm run check:local` | PASS | 退出码 0：Node UI 28 项、Rust workspace 145 项、Python 203 项（1 项因 Windows symlink 能力跳过）、Provider Skill 引用 33 项；含 Rust fmt/check/test/Clippy。环境：Windows 11 专业版 build 22000、Node 22.23.4、npm 11.19.0、Rust/Cargo 1.93.0、Python 3.11.4。|
| `npm run desktop:build` | PASS | 退出码 0；`target/release/wincraft-desktop.exe` 为 13,595,648 bytes，SHA-256 `64458EA768A36FE012230EA34D0E37936FB1ACF1FA74C1A49802C8D456BD7314`。旧 QA 宿主因锁定输出 EXE，已先按用户授权退出；本轮新构建未启动进行像素验收。|
| Commit `a78b3c9d4e9e19be7045faad4920d060f3c990c1` / `origin/dev` | PASS | 提交已推送到已核实的私有仓库 `exomind-team/WinCraft`，远端 `dev` 与提交一致。|
| Windows Actions run [41123291608](https://github.com/exomind-team/WinCraft/actions/runs/41123291608) | PASS | `gh run watch --exit-status` 退出码 0；Windows `source` job 完成，耗时 9m59s。Workflow 仅验证源码门禁，不替代原生 GUI 验收。|
| `npm run codegraph:sync` / `npm run codegraph:status` | PASS | 最终代码/格式化后同步 6 个变更文件；索引为 current（98 files、2,763 nodes、9,208 edges）。|
| 新编译 headless Rust Host + `scoped_live_sources.py --duration-seconds 5` | PASS（L4 protocol/source integration） | `cargo build -p wincraft-server --bin wincraft-headless` 退出码 0；使用 authority-expiry 修正后的二进制，Provider smoke 退出码 0，两个独立本地来源 Provider lease 并发重叠 4.89 秒；Codex 为 `online → stale → revoked`，Claude Code 为 `online → stale → stale`；父 Provider 更新 lifecycle panel 并确认销毁临时世界。终端摘要只含汇总字段，无会话标题、项目、ID 或 Agent 输出。|
| 首次撤销路径尝试 | FAIL（已修复并重跑） | 退出码 1，`SCOPE_REVISION_CONFLICT`：父 Provider 在写入 stale 状态后未使用返回的新 scope revision。修复为每次写入后传递新 revision；修复后的同一真实 Host smoke 退出码 0。|
| headless Host / runtime descriptor 清理 | FAIL | 最终 TTY 启动的 Host 已清理本次 descriptor，Provider 子进程和临时世界已清理，headless 进程数为 0；ignored local directory 仍留 1 个来自此前非 TTY stop 的旧 runtime descriptor。Provider SDK 只在运行时解析 descriptor 以连接；我未手动检查或复制其内容，也未纳入 Git；旧描述文件清理仍需解决。|
| B08-03-A4 判定 | PARTIAL | Host 生命周期 API 与真实 Provider 状态转换已通过；`global_overview_provider.py` 仍使用合成会话记录，尚未把权威 Host 撤销状态并入选中 source/instance/session 的 detail/tombstone。当前未做桌面像素复验。|

忽略的本机汇总证据：`evidence/local/nextgen-2026-10-31/scope-status-lifecycle-smoke.json`。它不包含 runtime descriptor 内容；本机残留 descriptor 不属于证据文件。

## 2026-10-31 GitHub Actions checkpoint

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Commit `51be6bad6e3278a2888f2635f6510f06fd03f231` / `origin/dev` | PASS | 使用 `gh` 核对仓库为 `exomind-team/WinCraft` 私有仓库、默认分支 `dev`；提交推送成功，远端 `dev` 与本地 HEAD 一致。|
| Windows Actions run [41091337537](https://github.com/exomind-team/WinCraft/actions/runs/41091337537) | PASS | `Prototype verification (not native GUI acceptance)` 完成，`source` job 的 `npm run check:local` 成功，耗时 12m02s。该 workflow 不执行原生 UIA/托盘/多屏等人工验收。|
| Commit [`14a73ad`](https://github.com/exomind-team/WinCraft/commit/14a73adce8f238377195a51a4408566b51062e86) / `origin/dev` | PASS | 使用 GitHub CLI 核实私有仓库 `exomind-team/WinCraft` 的 `dev` 分支与本地提交一致。|
| Windows Actions run [41100209526](https://github.com/exomind-team/WinCraft/actions/runs/41100209526) | PASS | Actions run、check suite 与 `source` job 均 `completed/success`；`gh run watch --exit-status` 退出码 0，job 用时 12m01s。Workflow 不替代原生 UIA、托盘、多屏与人工交互验收。|
| Commit [`71d077c`](https://github.com/exomind-team/WinCraft/commit/71d077c5340ff2da59c7cc43d94ebdb5ddfa1f85) / `origin/dev` | PASS | B08-03-A4 missing-session detail behavior、本地回归与状态说明已提交推送；远端 `dev` 与该提交一致。|
| Windows Actions run [41105044150](https://github.com/exomind-team/WinCraft/actions/runs/41105044150) | PASS | `gh run watch --exit-status` 退出码 0；Windows `source` job `completed/success`，用时 8m08s。Workflow 只验证源码门禁，不替代原生 A4 撤销/按钮验收。|
| Commit [`69c3ec6`](https://github.com/exomind-team/WinCraft/commit/69c3ec668edb847153110bff352f4e508089ceab) / `origin/dev` | PASS | Provider 五课新增可选有界时长；默认交互模式不变，5 秒真实 Host synthetic smoke 已确认启动和自建世界清理。|
| Windows Actions run [41109395539](https://github.com/exomind-team/WinCraft/actions/runs/41109395539) | PASS | `gh run watch --exit-status` 退出码 0；run 与 check suite `completed/success`。Workflow 不替代五课交互、管理器清理或人工原生验收。|
| Commit `87964ce` / `origin/dev` | PASS | B05-02 合成 Tauri smoke 与状态记录已推送；`gh` 核对远端 `dev` 为该提交。|
| Windows Actions run [41178832248](https://github.com/exomind-team/WinCraft/actions/runs/41178832248) | PASS | `npm run check:local` 成功；source job 用时 12m18s。CI 不替代原生 UI 验收。|
| Commit `10a3df9` / `origin/dev` | PASS | B02-03 headless smoke 结果与 phase checkpoint 文档已推送；EXE/guide 本地 bundle 不作为 GitHub Release。|
| Windows Actions run [41179930393](https://github.com/exomind-team/WinCraft/actions/runs/41179930393) | PASS | `npm run check:local` 成功；source job 用时 9m12s。该提交只含文档与证据状态，不含产品运行时代码。|
| Commit `850ee0d` / `origin/dev` | PASS | B11-01 三轮 Provider crash/reacquire 证据与本机性能边界已同步；产品运行时代码未改。|
| Windows Actions run [41182047022](https://github.com/exomind-team/WinCraft/actions/runs/41182047022) | PASS | `npm run check:local` 全量门禁通过；source job 用时 12m05s。|

阶段性交付包（本机 Git 忽略）：`evidence/local/nextgen-2026-10-31/delivery-continuation-10a3df9/WinCraft-0.1.0-alpha.1-local-acceptance-20261031.zip`，含与 `9073b3b` 产品代码一致的 EXE、中文验收指南及当前 build/CI hash；不是 GitHub Release。

## 2026-10-31 B11-03 Linux capability/build check

**Given** Ubuntu 24.04 WSL2、`x86_64-unknown-linux-gnu` Rust target 和 Tauri GTK/WebKit/AppIndicator 构建依赖，**When** 使用独立 `/tmp` Cargo target 检查、测试并构建 workspace，**Then** Linux Rust/Tauri 编译边界通过；该证据不证明 GUI、托盘或窗口管理器行为等价。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Ubuntu WSL2 Tauri 依赖 | PASS（环境） | 安装 `libdbus-1-dev`、`libgtk-3-dev`、`libwebkit2gtk-4.1-dev`、`libayatana-appindicator3-dev`、`libxdo-dev`、`librsvg2-dev`；APT 解析共新增 189 个包、升级 14 个图形/系统依赖，使用 WSL root。H 盘构建空间紧张，Linux Cargo target 放在 `/tmp/wincraft-linux-target-1ced028`。|
| Linux `cargo fmt --all -- --check` | PASS | 退出码 0。环境：Ubuntu 24.04 WSL2、Linux kernel `6.6.114.1-microsoft-standard-WSL2`、x86_64、rustc/Cargo 1.96.0。|
| Linux `cargo test --locked --workspace --no-fail-fast` | PASS | 退出码 0：147 项通过（core 10、core invariants 62、desktop 22、server 53；无失败或跳过）。新增平台回归确认非 Windows 不广告外窗动作，并在执行时返回 unsupported。|
| Linux `cargo clippy --locked --workspace --all-targets -- -D warnings` | PASS | 退出码 0；包括 Tauri desktop 全 targets，无 warning。|
| Linux `cargo check --locked -p wincraft-desktop` | PASS | 退出码 0，无平台专用 unused warning。|
| Linux `cargo build --locked -p wincraft-desktop` | PASS（debug ELF） | 退出码 0；ELF 为 288,532,064 bytes，SHA-256 `eb5529e4890d2ae5bb85783256844395fa3b1427a77aeb57e2bc4e28f58211a8`，临时产物在 WSL `/tmp`。没有启动该 ELF。|
| Windows `npm run check:local` 当前工作树 | PASS | 退出码 0：UI 28、Rust 146、Python 205（1 项 symlink 能力跳过）、Clippy、离线契约与 Provider Skill 检查均通过。|
| Windows commit [`c836802`](https://github.com/exomind-team/WinCraft/commit/c8368023fba08ef620c56bb1a436e1c5e2d87ed6) `npm run desktop:build` / Actions [41140899841](https://github.com/exomind-team/WinCraft/actions/runs/41140899841) | PASS | Release build 退出码 0；EXE 为 13,595,648 bytes，SHA-256 `A09C1CA0E1D5CCB86131A94AE51EC2BEAE1592530952880EFB3CCDB5E48EB6CB`。Windows source job 的 `npm run check:local` 通过（11m43s）。没有启动窗口，故不增加原生 UI 验收证据。|
| 本机 Windows EXE + 中文验收包 | PASS | `evidence/local/nextgen-2026-10-31/WinCraft-alpha1-acceptance-delivery-b11-03.zip`，4,352,029 bytes，SHA-256 `19C6CA0EAD96A86213E90A76B09597DA04A69D45E0115B9B96CA6054731D45F0`；仅含 EXE、中文验收指南与 BUILD.txt，包内 EXE SHA 与上方提交一致。runtime descriptor、凭据和业务数据均未打入包。|
| Linux WSLg/X11/Wayland 原生交互、macOS 构建/交互 | NOT_RUN | WSLg 有 `DISPLAY=:0` 与 `WAYLAND_DISPLAY=wayland-0`，但没有启动 GUI 或读取窗口树；X11/Wayland 分别验收与 macOS host 均未运行。 |
| B11-03-A1/A2/A3 | PASS / PARTIAL / PASS（受限） | A1 明确区分 Tauri 编译与原生交互。A2 已给出源代码与 Linux 构建能力矩阵，但原生 Linux GUI 与 macOS 仍 NOT_RUN，故 PARTIAL。A3 Windows 全门禁与 release build 通过；改动仅收窄 Windows-only helper 编译边界并新增平台 capability 回归，未改变 Windows API 路径。B11-03 保持 `IMPLEMENTED_UNVERIFIED`，B11-01 性能基线仍单独未关闭。|

详细平台边界见 [`docs/platforms/capability-matrix.md`](../platforms/capability-matrix.md)。本机补充证据 `evidence/local/nextgen-2026-10-31/b11-03-linux-platform-build.json` 默认忽略，不提交 Cargo target、runtime descriptor 或 WSL 系统依赖包。

## 2026-10-31 B05-02 Codex opt-in quota source

**Given** 合成 Codex auth 文件与合成 usage 响应，**When** 来源未启用或 Provider 显式传入 `--codex-quota`，**Then** 未启用时不读凭据也不联网；启用时只投影主/次窗口的剩余比例与时间，不公开令牌/账户 ID；账号切换或身份无法确认时清掉旧读数，普通网络失败则保留并标为读取失败。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest tests.test_codex_quota tests.test_team_sense_quota -v` | PASS | 22 项定向合成测试通过：固定 HTTPS GET、重定向拒绝、响应/凭据大小上限、无效值不变零、极值拒绝、凭据脱敏、账号切换清理与默认未启用不读取。未读取真实 `auth.json`，HTTP opener 全部为模拟对象。|
| `npm run check:python` | PASS | 216 项测试通过，1 项因当前 Windows symlink 创建能力不可用而跳过；Provider Skill 引用 33/33 通过。第一次运行因测试导入了另一集成的同名 `provider` 模块而失败；将 disabled-source 回归收窄至独立 Codex quota adapter 后整套重跑通过。|
| `python scripts/check_contracts.py` / handoff validator | PASS | 离线协议/fixture 检查通过；handoff 一致性检查报告 43 文档、143 相对链接、74 条需求、48 个任务、155 个验收项且无错误。|
| `cargo build --locked --release -p wincraft-server --bin wincraft-headless` | PASS | 退出码 0；新建 `target/release/wincraft-headless.exe`，3,240,960 bytes，SHA-256 `87DAA64BA9F973AB84996FFD9811C3B54CD052F3C8ACD0894DDF8BF086DF373B`。|
| 新建 release headless Rust Host + Provider `--demo --duration-seconds 3` | PASS（L2 WebSocket/场景） | 退出码 0；真实 Rust Host 接受含 Codex 双窗口、MiniMax 周期条与 DeepSeek 独立币种的合成场景，Provider 清理了自己的临时世界。runtime descriptor 在专用临时目录中短暂存在，未写入证据，测试后进程与文件均已清理。Demo 无凭据读取、无外部网络请求。|
| Commit f03be18 / GitHub Actions run 41149432751 | PASS | 私有 `origin/dev` 已推送；Windows source job 的 `npm run check:local` 完成成功，用时 12m45s。该 CI 验证配额 HUD 提交，不替代当前后续 B06 本地改动的 CI 或原生像素验收。|
| `npm run codegraph:sync` / `npm run codegraph:status` | PASS | 索引 current：100 个文件、2,856 个节点、9,470 条边。|
| Codex/TeamSense 实时账户数据、当前桌面像素 | NOT_RUN | 未读取用户 Codex auth 文件、未发送 Codex/TeamSense 请求，也没有运行当前桌面 UI 截图。Codex route 是未公开稳定契约，故保持默认关闭与实验性说明；真实账号新鲜度与视觉验收不宣称通过。|
| B05-02-A1/A2/A3/A4 | PARTIAL / PARTIAL / PARTIAL / PARTIAL | 合成模型、账户切换和来源隔离规则已测；TeamSense 账户归属、真实服务 freshness 与当前窗口像素仍待验收。B05-02 维持 `IMPLEMENTED_UNVERIFIED`。|

本机脱敏证据 [`b05-02-codex-quota-optin.json`](../../evidence/local/nextgen-2026-10-31/b05-02-codex-quota-optin.json) 被 `.gitignore` 忽略，仅记命令与汇总结果，不含令牌、账户 ID、runtime descriptor 或业务数据。

## 2026-10-31 B05-02 synthetic quota scene on Tauri release

**Given** 当前标准 Tauri release 与 demo-only quota Provider；**when** `--demo --duration-seconds 3` 创建场景并结束；**then** 真实 Host 接受窗口 capability 和合成 Codex/MiniMax/DeepSeek 场景，Provider 退出码为 0 并清理自有世界。此项验证 Tauri Host 集成路径，不验证像素或用户账户。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python examples/integrations/model_quota/provider.py --runtime <actual descriptor> --demo --duration-seconds 3` | PASS（Tauri Host / synthetic only） | 退出码 0；`capabilities_accepted=true`、`scene_created=true`、`world_cleanup_confirmed=true`。无 credentials read、无网络请求，descriptor 仅由 SDK 短暂读取并在清理时删除。|
| 当前像素与真实来源 | NOT_RUN | Computer Use native pipe 无法连接；TeamSense token/Codex opt-in 未提供，故未发真实 API 请求、未读 `auth.json`。|
| B05-02-A1/A2/A3/A4 | PARTIAL / PARTIAL / PARTIAL / PARTIAL | 本 smoke 加强真实 Tauri scene/cleanup 证据；账户归属、缓存时效/断线实际窗口呈现、真实 GET 和 Codex 身份/像素边界仍未验证。任务保持 `IMPLEMENTED_UNVERIFIED`。|

本机合成 smoke 汇总 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b05-02-quota-tauri-20261031-145409/summary.json) 在忽略的 `evidence/local/`；不含 runtime descriptor、账户标识或原始 provider 输出。

## 2026-10-31 B06-03 Manager permission/re-preview and stale-action regression

**Given** 一个需要 `metrics.read`、inventory 中存在已声明但尚未授权的合成 Provider；**When** 内部 Manager 通过通用组件场景触发 `pack.grant`；**Then** 成功授权后旧 preview 被撤销、generation 变化后立即生成新 preview，已授权候选不再显示空权限 grant 按钮，只有新 `Ready` preview 可以创建 world 并将单窗写租约交给该 Provider。若 inventory 在点击旧 grant 动作前变化，Host 返回 `STALE_PLAN`、Manager 清除旧 preview 并显示重新规划提示，且不创建 world。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| 首次 `cargo test --locked -p wincraft-server manager_permission_button_grants_then_repreviews_before_apply -- --nocapture` | FAIL（已修复） | 退出码 1；发现已授权且已选中的候选仍被渲染为 `pack.grant` 按钮，显示空权限并会收到 `NO_PERMISSION_REQUIRED`。这是真实 Manager scene 逻辑缺陷，不是测试夹具问题。|
| 修复后的定向管理器流程测试 | PASS | 相同命令退出码 0；测试从 Manager 场景读取实际 `pack-grant` 静态动作，授权后检查新的 preview ID 与 inventory generation、旧 preview `PLAN_NOT_FOUND`、grant 按钮消失、apply 按钮出现，最终导入 Provider 获得该 world 的 writer。|
| 首次 `cargo test --locked -p wincraft-server stale_permission_action_clears_the_manager_preview_and_shows_replan_notice -- --nocapture` | FAIL（已修复） | 退出码 1；先复现到 generation 改变时 `authorize_pack_binding` 返回 `STALE_PLAN`，但 Manager 内存仍保留旧 preview。|
| 修复后同一 stale-action 定向测试 | PASS | 退出码 0；拒绝旧 grant 动作、清空 preview、显示本地化重新规划 notice，world 数量保持不变；错误仍通过 `action.result` 回执，不绕过 Host 授权。|
| `cargo test --locked -p wincraft-server stale_ -- --nocapture` | PASS | 2 项过期 grant 回归通过：Host 判定当前 preview 过期时清除它；旧渲染动作到达时保留管理器更新后的有效 preview。|
| `cargo fmt --all -- --check` / `cargo check --locked -p wincraft-server` | PASS | 分别退出码 0；格式检查与 server 编译通过。|
| `cargo test --locked -p wincraft-server --no-fail-fast` | PASS | 56 项 server 单测通过，0 失败；包含成功授权/重规划/应用以及两种过期动作边界回归。|
| `cargo clippy --locked -p wincraft-server --all-targets -- -D warnings` | PASS | 退出码 0，无 warning。|
| `npm run check:local` | PASS | 退出码 0：28 项 Node UI、149 项 Rust workspace、216 项 Python（1 项 Windows symlink 能力跳过）；Rust fmt/check/test/Clippy、离线契约和 33 个 Provider Skill 引用均通过。环境：Windows 11 build 22000、Node 22.23.4、npm 11.19.0、Rust/Cargo 1.93.0、Python 3.11.4。|
| `npm run desktop:build` | PASS | 退出码 0；提交 `9073b3b` 的 release `target/release/wincraft-desktop.exe` 为 13,600,256 bytes，SHA-256 `7E910E01057DADB17991B00D2A51CE63419628F818C35C06C1EE3D0C3179D691`。该 EXE 已独立启动并通过下方真实 Tauri Host probe；本轮未打开管理器 UI，也未做像素/鼠标验收。|
| release headless Rust Host + `python examples/python/lease_probe.py --runtime <isolated descriptor>` | PASS | `cargo build --locked --release -p wincraft-server --bin wincraft-headless` 和真实 Host 上的 Provider probe 均退出码 0，41 项协议检查通过；临时世界由 probe 清理，Host 停止，isolated descriptor 已删除。只用合成数据与 loopback，不访问账户/API。脱敏汇总位于忽略目录 `evidence/local/nextgen-2026-10-31/b06-03-final-host-1793408885298/summary.json`。|
| 独立启动当前 Tauri release + Python `lease_probe.py` | PASS | 无参数启动 `target/release/wincraft-desktop.exe`（tray-only 默认启动），真实 Tauri Host 上的 Provider probe 退出码 0，41 项检查通过；Provider 临时世界清理、Host 停止、该 Host 的 runtime descriptor 精确删除。一次 `LOCALAPPDATA` 隔离尝试未被 Tauri Known Folder resolver 采用；随后从 Host 日志定位并清理本次创建的 descriptor，再以默认路径完成成功 smoke。未读取 descriptor 内容或记录 bearer token。管理器 UI 像素/点击仍 NOT_RUN。忽略目录脱敏汇总：`evidence/local/nextgen-2026-10-31/b06-03-tauri-release-1793409332677/summary.json`。|
| `npm run codegraph:sync` / `npm run codegraph:status` | PASS | 同步 1 个 Rust 文件；索引 current：100 files、2,866 nodes、9,542 edges。|
| GitHub Actions run [41151206263](https://github.com/exomind-team/WinCraft/actions/runs/41151206263) | PASS（旧提交） | Windows source job 对 commit `17ddee4` 完成成功；它早于本机新增 stale-action 修复，不计作该修复的 CI 证据。|
| Commit `9073b3b` + docs `8bee25d` / Windows Actions run [41154964442](https://github.com/exomind-team/WinCraft/actions/runs/41154964442) | PASS | `dev` 已推送；Windows `source` job 的 `npm run check:local` 完成成功，耗时 12m32s。覆盖 Manager stale-action fix 和验收文档；该 workflow 不替代原生 GUI 验收。|
| 重复 release build hash | NOT_DETERMINISTIC（待调查） | 两次此前 B06 build、源码输入未改时的 `npm run desktop:build` 分别得到 SHA-256 `D0DA99635BB206BBEE4F31CF06B7DEA7D9F357D3A40CD138DADC65147E56A34B` 与 `A0A4981ECCD9710BA0B44A54D0A23749A7AFBC0EF5FCB383AD117D7716D160EB`，文件大小相同；后一产物 PE TimeDateStamp 为 `2026-10-31 08:40:39`。这说明相同源码可能含时间相关构建差异，但具体原因尚未验证；当前工作树的 SHA-256 绑定于本次实际产物，不宣称可复现 hash。|
| B06-03-A1/A2/A3 | PARTIAL / PARTIAL / PARTIAL | Host 与 Manager action 路由增加了更强的 L1-L2 证据；Computer Use/UIA 不可用，Windows release 的人工预览、授权、应用、回执、取消和回退路径仍未验收。|

本机脱敏回归摘要 [`b06-03-manager-permission-repreview.json`](../../evidence/local/nextgen-2026-10-31/b06-03-manager-permission-repreview.json) 位于默认忽略的 `evidence/local/`；不含 runtime descriptor、Provider source 内容或业务数据。

## 2026-10-31 B11-01 short Windows Tauri process-tree and RPC baseline

**Given** 提交 `9073b3b` 的 Windows Tauri release、一个显示内部 Manager 的窗口和 repository-owned synthetic `lease_probe.py` Provider；**When** 运行 60 秒 WMI process-tree sampler 并执行合成 create/destroy/snapshot/data-replace/reconnect 探针；**Then** 记录本机与版本、release hash、负载规模、进程树/句柄/内存/CPU，以及本机环回请求的 p50/p95/p99；清理所有合成世界和 runtime descriptor。该场景只形成短时样本，不证明长期泄漏/睡眠恢复或跨机器表现。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `tests/measure_windows_process_tree.ps1 -RootProcessId <Tauri PID> -DurationSeconds 60 -SampleIntervalMilliseconds 1000` | PASS（一次 context-complete 短时样本） | Windows 11 Pro build 22000；AMD Ryzen 9 9950X 16-Core、32 logical processors；Rust/Cargo 1.93.0、Python 3.11.4；Tauri EXE 为 13,600,256 bytes，SHA-256 `7E910E01057DADB17991B00D2A51CE63419628F818C35C06C1EE3D0C3179D691`。61.203 秒、32 个样本，WMI query 开销使实际 median/p95 cadence 为 1.919/2.145 秒。`powercfg` 前后均为 `Turbo`，WMI 显示 0 battery devices 且没有 ACPI power-source provider；未注入 sleep/wake。进程树包含 `wincraft-desktop.exe` 与 `msedgewebview2.exe`，峰值 8 个进程、工作集 580,329,472 bytes、private bytes 394,821,632、4,262 handles、357 threads；p95 machine CPU 1.489%、p95 one-core CPU 47.632%。|
| Tauri release + `python examples/python/lease_probe.py --runtime <actual descriptor>` | PASS | tray-only 协议 probe 41 项通过；包含 lease expiry/reacquire、断线重连和 1,024 × 32 KiB slow-reader 配置。该 slow-reader 的实际 achieved message rate 未单独计量。|
| `python tests/performance_probe.py --runtime <actual descriptor> --world-cycles 50 --snapshot-iterations 200 --data-iterations 100 --payload-bytes 1024 --reconnect-cycles 20 --inter-call-interval-ms 25`（同一 context 下两次） | PASS（合成 loopback） | 每次 50 次 world create/destroy、200 次 snapshot、100 次 raw `data.replace`、20 次断线后 writer reconnect/join。两次 p95 ms（run1/run2）：create 9.778/1.710，destroy 1.325/1.353，snapshot 1.409/1.280，data.replace 1.592/1.513，reconnect+join 2.760/2.999；两次最大观察值分别为 36.156/41.855/26.206/35.827/3.763 ms。电源计划前后保持 `Turbo`；调用按 25 ms 间隔串行，RTT 是本机环回，不代表 UI 延迟或并发吞吐；尾部尖峰保留且不平均。|
| runtime descriptor、Host 和 Provider 临时世界清理 | PASS | Tauri Host 已停止；只删除本次 Host 日志标识的确切 descriptor；Provider probe 正常清理自有世界。descriptor 内容从未读取；保留的 process-tree 和 latency JSON 仅含聚合进程名/计数及合成样本，不含 PID、用户路径或 token。|
| `npm run check:local` after adding the probes | PASS | 退出码 0：UI 28、Rust workspace 149、Python 220（1 项 Windows symlink 能力跳过），Clippy、合同检查、33 个 Provider Skill 引用通过。PowerShell sampler 的 parser/self-smoke 和 performance percentile 的 4 项单元测试通过。|
| Commit `31d7675` / Windows Actions run [41161166248](https://github.com/exomind-team/WinCraft/actions/runs/41161166248) | PASS | Windows `source` job 的 `npm run check:local` 完成成功，用时 10m24s。CI 验证源码和离线门禁；WMI process-tree/runtime measurements 是本机实测，CI 未执行。|
| B11-01-A1/A2/A3 | PASS（context-complete sample） / NOT_RUN / PASS | A1 的机器、版本、负载、运行时长和电源计划上下文已记录；WMI 没有提供 ACPI power-source state，因此电源来源本身仍未知。A2 的长期 idle/refresh 趋势、crash cleanup、sleep/wake 和阈值 ADR 尚未执行；A3 继续禁止把短时样本宣传成轻量、无泄漏或性能保证。任务保持 `IMPLEMENTED_UNVERIFIED`。|

本次忽略的 context-complete 本机证据位于 [`b11-01-contextual-1793415605844`](../../evidence/local/nextgen-2026-10-31/b11-01-contextual-1793415605844/)；包括 aggregate `summary.json`、`process-tree-samples.json` 和两次 synthetic latency JSON。runtime descriptor、原始 Host log 和 lease-probe 输出已删除。

## 2026-10-31 B11-01 visible synthetic refresh soak

**Given** 同一份 `9073b3b` Windows Tauri release 与 repository-owned synthetic Provider；**when** Provider 保持 320 × 200 世界可见，每 5 秒更新一次合成计数，共运行 5 分钟，同时以 5 秒请求间隔采集进程树；**then** 60 次更新均获得回执，Provider 清理自有世界，WebView 子进程退出。此场景补充短时刷新观察，不等同于长期无泄漏验收。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `tests/performance_probe.py --runtime <actual descriptor> --world-cycles 1 --snapshot-iterations 1 --data-iterations 1 --payload-bytes 128 --reconnect-cycles 1 --soak-seconds 300 --refresh-interval-seconds 5 --soak-visible` | PASS（合成可见刷新） | 60 次 `data.replace` 更新，事务延迟 p50/p95/p99/max 为 1.524/12.018/35.939/35.939 ms。无 revision conflict 被误当作写入成功；probe 经 SDK `mutate` 仅在明确 `REVISION_CONFLICT` 时刷新 revision。|
| `tests/measure_windows_process_tree.ps1 -RootProcessId <Tauri PID> -DurationSeconds 330 -SampleIntervalMilliseconds 5000` | PASS（bounded sample） | 实测 333.434 秒、56 个样本；采样 median/p95 间隔 5.940/6.237 秒；峰值 7 个进程、367,558,656 bytes working set、202,756,096 private bytes、3,655 handles、297 threads；p95 CPU 为 machine-normalized 0.050%、one-core-normalized 1.607%。活跃窗口首尾 5 个样本中位数：working set 355,131,392 → 366,673,920 bytes，private bytes 202,338,304 → 186,630,144 bytes，handles 3,562 → 3,583，threads 289 → 277。世界销毁后 8 个连续样本只剩 tray Host（28,262,400 bytes working set、7,020,544 private bytes、353 handles、40 threads）。|
| 电源与睡眠上下文 | PARTIAL | 采样前后电源计划均为 `Turbo`；WMI 报告 0 battery devices 且没有 ACPI power-source provider，物理电源来源未知；未注入 sleep/wake。|
| Provider/Host/runtime descriptor 清理 | PASS | Provider 进程结束并确认只销毁自己的世界；核对精确 EXE 后停止本次 release Host，移除其本地 runtime descriptor。raw Provider/Host logs、PID 文件和 descriptor 路径文件已删除。|
| `npm run check:local` after the refresh and Host-disconnect probe additions | PASS | 退出码 0：UI 28、Rust workspace 149、Python 225（1 项 Windows symlink 能力跳过），Clippy、合同检查、33 个 Provider Skill 引用通过。|
| B11-01-A1/A2/A3 | PASS / PARTIAL / PASS | A2 仅推进到 PARTIAL：5 分钟样本未显示活跃期 private-byte 中位数上行，Provider 清理后 WebView 子进程退出；一次 abrupt Provider exit 也通过 stale/reacquire/epoch fence/自有世界清理。仍不能断言长期 leak-free，也未验证 Host-crash、sleep/wake 或资源阈值 ADR。任务仍为 `IMPLEMENTED_UNVERIFIED`。|

本机聚合证据 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b11-01-soak-1793417556075/summary.json) 与 [`process-tree-samples.json`](../../evidence/local/nextgen-2026-10-31/b11-01-soak-1793417556075/process-tree-samples.json) 位于忽略的 `evidence/local/`；未保留运行时描述、凭据、PID 或原始日志。

## 2026-10-31 B11-01 abrupt synthetic Provider crash recovery

**Given** 当前 checkout 的 release headless Rust Host 与一个通过共享 SDK 建立的合成 writer；**when** 父进程强制结束该 owner Provider 子进程；**then** recovery Provider 先读到 `stale`，随后以更高 lease epoch 获得 writer 权限，删除自有世界，并确认后续 snapshot 返回 `NOT_FOUND`。父进程停止精确 headless Host 并移除该 Host 创建的 runtime descriptor。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo build --locked --release -p wincraft-server --bin wincraft-headless` | PASS | 退出码 0；Windows 11 Pro build 22000；checkout `71d92fd`；artifact `target/release/wincraft-headless.exe` SHA-256 `1BB21942FA052A900088624095438ACA9ACCF9B5D6E3B1E3C954D3E6EF8131B4`。|
| `python tests/crash_recovery_probe.py --runtime <actual descriptor> --record-file <ignored local private record>` | PASS | 退出码 0；`owner_process_terminated`、`stale_status_observed`、`writer_reacquired`、`lease_epoch_advanced` 和 `synthetic_world_destroyed` 全部为 true；IDs/join key/lease 不在聚合输出中。|
| `Host`、descriptor 与私有记录清理 | PASS | 精确 headless Host 已停止，descriptor 与临时 owner record 已删除；本机汇总证据不含 PID、descriptor 路径或 Provider 原始输出。|
| B11-01-A2 | PARTIAL | 一次 Provider 进程崩溃后重获 writer 的真实 Host 路径通过；headless Host 强制停止后的 Provider 断线事件也通过。Tauri/WebView 子进程清理、重复崩溃循环、长时趋势、sleep/wake 与阈值 ADR 仍 NOT_RUN。|

本机汇总 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b11-01-crash-20261031-121253/summary.json) 保存在忽略的 `evidence/local/`；Host descriptor、owner record 和进程信息没有保留。

## 2026-10-31 B11-01 三轮 Provider crash/reacquire

**Given** 当前 release headless Rust Host；**when** 串行运行三轮合成 owner Provider 崩溃探针；**then** 每轮都观测到 `stale`、以更高 epoch 重获 writer、销毁仅属于该轮的世界并验证 `NOT_FOUND`。这补强了 Provider 崩溃恢复的可重复性，但不覆盖 Host 崩溃循环、sleep/wake 或长期泄漏。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python tests/crash_recovery_probe.py --runtime <ephemeral descriptor> --record-file <ephemeral record>` × 3 | PASS（3/3） | 每轮退出码 0；`owner_process_terminated`、`stale_status_observed`、`writer_reacquired`、`lease_epoch_advanced`、`synthetic_world_destroyed` 与 `private_record_removed` 全部为 true。|
| `python -m unittest tests.test_crash_recovery_probe -v` | PASS | 3 项探针记录/终态事件单测通过。|
| Host 与临时记录清理 | PASS / NOT_TESTED | 三个私有 owner record 均已删除；测试 Host 在全部 cycle 后由 runner 终止，descriptor 随临时目录销毁；未将这次清理计作 graceful Host shutdown。|
| B11-01-A2 判定 | PARTIAL | 三轮 Provider crash/reacquire 可重复通过；长时无泄漏、重复 Host crash/restart、sleep/wake 与阈值 ADR 仍 NOT_RUN。|

忽略的聚合证据 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b11-01-repeated-crash-recovery-20261031/summary.json) 只保留 cycle 结果与 Host artifact hash，不含 owner/world ID、join key、PID、descriptor 路径或原始输出。

## 2026-10-31 B11-01 forced headless Host shutdown

**Given** release `wincraft-headless` Host 与持有合成世界的 Python Provider；**when** parent 强制终止本次 Host 进程；**then** Provider 收到 SDK `connection.error` 并自行退出，Host descriptor 和 ready marker 被删除。此项只验证 headless transport；Tauri/WebView 子进程另见后续实测。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python tests/crash_recovery_probe.py --runtime <actual descriptor> --record-file <ignored local ready marker> --expect-host-disconnect` | PASS | Provider 创建合成世界后等待 Host 断线；强制关闭精确 headless Host 后收到 `connection.error`，退出码 0。聚合结果只记录事件类别，不包含 world ID、join key、lease 或错误文本。|
| Host、descriptor 与 Provider 清理 | PASS | headless Host 已停止；精确 descriptor 与 ready marker 已删除；raw 输出及 PID 文件未保留。|
| B11-01-A2 | PARTIAL | 一次 headless Host shutdown → Provider disconnect 已验证；Tauri/WebView 子进程 crash 回收另有一轮通过；重启恢复、重复 Host crash、sleep/wake、长期泄漏趋势和阈值 ADR 仍 NOT_RUN。|

本机汇总 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b11-01-host-crash-20261031-124420/summary.json) 位于忽略的 `evidence/local/`；没有 descriptor、PID 或原始 Provider 输出。

## 2026-10-31 B11-01 三轮 headless Host crash/disconnect

**Given** 三个顺序启动的隔离 release headless Host 与各自的合成 Provider；**when** 每轮 Provider 创建合成世界后，测试器强制终止该轮唯一的 Host 进程；**then** Provider 收到 `connection.error` 并以退出码 0 结束，随后新 Host 可以接受下一轮连接。该项证明重复 headless transport disconnect 路径，不证明 Host graceful shutdown 或 Tauri/WebView 进程树重启。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python tests/crash_recovery_probe.py --runtime <ephemeral descriptor> --record-file <ephemeral marker> --expect-host-disconnect` × 3 | PASS（3/3） | 三轮均创建合成世界；每次只终止测试器启动的 Host；Provider 都观察到 `connection.error` 并以退出码 0 清理自身连接。|
| Host、Provider 与临时资源清理 | PASS / PARTIAL | 三个 Host 与 Provider 全部退出，ready marker 均删除；强制终止的 Host 未自行删除 descriptor，由隔离临时目录在每轮结束时清理。未将此项记录为 graceful shutdown。|
| B11-01-A2 判定 | PARTIAL | 三轮 headless Host disconnect 通过；重复 Tauri/WebView crash/restart、sleep/wake、长期泄漏趋势与阈值 ADR 仍 NOT_RUN。|

忽略的聚合证据 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b11-01-repeated-host-disconnect-20261031/summary.json) 只保留每轮终态事件/退出码与 Host artifact hash，不含 world ID、ready marker 路径、PID、descriptor 内容或原始输出。

## 2026-10-31 B11-01 fifteen-minute visible refresh soak

**Given** 同一份 `9073b3b` Windows Tauri release 与合成 Provider；**when** 保持 320 × 200 世界可见并每 5 秒刷新合成计数 15 分钟，同时用 WMI 采集 Host/WebView 进程树；**then** 180 次更新完成，Provider 清理世界，WebView 子进程退出。该样本延长活动刷新观察，不等同于长期无泄漏验收。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `tests/performance_probe.py --runtime <actual descriptor> --world-cycles 1 --snapshot-iterations 1 --data-iterations 1 --payload-bytes 128 --reconnect-cycles 1 --soak-seconds 900 --refresh-interval-seconds 5 --soak-visible` | PASS（合成可见刷新） | 180 次 `data.replace` 更新；事务延迟 p50/p95/p99/max 为 1.683/6.653/23.050/41.275 ms；`cleanup_confirmed=true`。|
| `tests/measure_windows_process_tree.ps1 -RootProcessId <Tauri PID> -DurationSeconds 930 -SampleIntervalMilliseconds 5000` | PASS（bounded sample） | 实测 931.6 秒、152 个样本；median/p95 采样间隔 6.122/6.434 秒；峰值 7 个进程、377,720,832 bytes working set、207,622,144 private bytes、3,680 handles、303 threads；p95 CPU machine/one-core-normalized 为 0.049%/1.555%。活跃期首尾 5 样本中位数：working set 359,313,408 → 376,774,656 bytes，private bytes 206,450,688 → 196,370,432 bytes，handles 3,549 → 3,568，threads 290 → 271。销毁世界后 5 个连续样本只剩 tray Host（31,748,096 bytes working set、7,995,392 private bytes、336 handles、40 threads）。|
| 电源上下文与清理 | PASS / PARTIAL | `Turbo` 在采样前后保持不变；WMI 报告 0 battery devices 且无 ACPI power-source provider，实际电源来源未知。Host 已停止，runtime descriptor 已删除，未注入 sleep/wake。|
| B11-01-A2 | PARTIAL | 与先前 5 分钟样本一样，15 分钟活跃期私有内存中位数没有上行，世界清理后只剩 Host；这些样本仍不足以证明长期 leak-free。单次 Provider crash/reacquire 与 headless Host 断线已另行通过；Tauri/WebView crash cleanup、sleep/wake 与阈值 ADR 仍 NOT_RUN。|

本机聚合证据 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b11-01-refresh-long-20261031-121838/summary.json) 与 [`process-tree-samples.json`](../../evidence/local/nextgen-2026-10-31/b11-01-refresh-long-20261031-121838/process-tree-samples.json) 在忽略的 `evidence/local/`；仅保留聚合数据，不含 PID、runtime path、descriptor、token 或 Provider 原始输出。

## 2026-10-31 B11-01 forced Tauri Host shutdown and WebView cleanup

**Given** 当前 release `wincraft-desktop.exe` 与一个可见的合成世界；**when** synthetic Provider 创建窗口后 parent 强制结束该 Tauri Host；**then** Provider 收到 `connection.error`，并在 Host 退出后 3 秒内所有 WebView2 后代进程均自行结束。精确 Tauri descriptor 已移除，没有遗留本次 Host 的 WebView 子进程。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python tests/crash_recovery_probe.py --runtime <actual descriptor> --record-file <ignored local ready marker> --expect-host-disconnect --visible-window` + 精确 Tauri root termination | PASS（process tree） | Tauri EXE SHA-256 `7E910E01057DADB17991B00D2A51CE63419628F818C35C06C1EE3D0C3179D691`；Provider 收到 `connection.error` 并退出。终止前识别 6 个 WebView2 后代，3 秒后剩余 0，探针没有手动杀 WebView 子进程。|
| UI pixels / window interaction | NOT_RUN | Computer Use native pipe 在重试与 JS kernel reset 后仍不可用；本项只证明 Tauri 进程与 WebView 子进程生命周期，不证明屏幕内容、鼠标或标题栏行为。|
| Host、descriptor、Provider 与 WebView 子进程清理 | PASS | 精确 Tauri Host 已停止；descriptor、ready marker、Provider 输出与 PID 文件已删除；进程树中无本次 Host 的剩余后代。|
| B11-01-A2 | PARTIAL | 一次 Tauri 强制退出后 6 个 WebView 后代均自行退出；长时趋势、重复 crash/restart、sleep/wake 和阈值 ADR 仍 NOT_RUN。|

本机聚合证据 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b11-01-tauri-crash-20261031-130240/summary.json) 在忽略的 `evidence/local/`；没有保存进程 ID、descriptor 路径或窗口截图。

## 2026-10-31 B11-01 thirty-minute visible refresh soak

**Given** 同一份 `9073b3b` Windows Tauri release 与合成 Provider；**when** 320 × 200 世界保持可见并每 5 秒刷新计数 30 分钟，同时采集进程树；**then** 360 次更新完成，Provider 清理世界，WebView 子进程退出，清理后连续 5 个样本只剩 Host。此 30 分钟样本仍不构成长时无泄漏承诺。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `tests/performance_probe.py --runtime <actual descriptor> --world-cycles 1 --snapshot-iterations 1 --data-iterations 1 --payload-bytes 128 --reconnect-cycles 1 --soak-seconds 1800 --refresh-interval-seconds 5 --soak-visible` | PASS（合成可见刷新） | 360 次 `data.replace` 更新，p50/p95/p99/max 为 1.602/11.845/29.075/43.275 ms；`cleanup_confirmed=true`。|
| `tests/measure_windows_process_tree.ps1 -RootProcessId <Tauri PID> -DurationSeconds 1830 -SampleIntervalMilliseconds 5000` | PASS（bounded sample） | 实测 1,830.697 秒、303 点；median/p95 间隔 6.062/6.326 秒；峰值 7 个进程、375,549,952 bytes working set、206,430,208 private bytes、3,623 handles、301 threads；p95 CPU machine/one-core-normalized 为 0.041%/1.327%。首尾 5 点中位数：working set 354,414,592 → 374,341,632 bytes，private bytes 205,438,976 → 200,908,800 bytes，handles 3,475 → 3,483，threads 288 → 268。清理后 5 点只剩 tray Host（26,324,992 bytes working set、6,979,584 private bytes、292 handles、38 threads）。|
| 电源、清理与 A2 状态 | PASS / PARTIAL | `Turbo` 前后不变；0 battery devices、无 ACPI power-source provider；未注入 sleep/wake。Host、descriptor 和 PID/path 文件已清理。30 分钟活跃期 private-byte 中位数下降，working set 上升约 20 MB；不足以证明长期趋势，A2 仍 PARTIAL。|

本机汇总 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b11-01-refresh-30m-20261031-130727/summary.json) 与 [`process-tree-samples.json`](../../evidence/local/nextgen-2026-10-31/b11-01-refresh-30m-20261031-130727/process-tree-samples.json) 位于忽略的 `evidence/local/`；只保留聚合测量，不含 PID、runtime path、descriptor 或 token。

## 2026-10-31 B11-04 offline pre-release audit

**Given** baseline `6929056700b1ba6702288534579debc8a502c139` and current `dev` checkout; **when** compare license/name/ownership files, query the connected GitHub repository and release inventory, and inspect the versioned Chinese/English release documents; **then** confirm the repository remains private, no GitHub Release or tag exists, no license/name/owner migration occurred, and release materials state version/update date and the unverified native gates. A local acceptance ZIP is a test artifact, not publication.

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Baseline license, product/package names and ownership | PASS | `git diff <baseline>..HEAD -- LICENSE LICENSE-NOTES.md` has no changes; `package.json` remains `wincraft-prototype`, Tauri crate remains `wincraft-desktop`, and the verified remote is `exomind-team/WinCraft` on `dev`. No ownership or visibility change was made.|
| GitHub Release/tags and publication boundary | PASS | `gh repo view` reports `PRIVATE`; `gh release list` returns `[]`; `git tag --list` is empty. No remote release, tag, installer or public upload was created.|
| Public-facing release documentation | PASS | README names `0.1.0-alpha.1` and `2026-10-31`; Chinese acceptance guide front matter has matching version/update date; English `docs/release-gate.md` is current and lists known limits. Handoff validation reports 43 documents and 143 relative links with no errors.|
| Local EXE + Chinese guide package | PASS | [`WinCraft-0.1.0-alpha.1-local-acceptance-20261031.zip`](../../evidence/local/nextgen-2026-10-31/delivery-b11-04-20261031-140158/WinCraft-0.1.0-alpha.1-local-acceptance-20261031.zip) is 4,558,082 bytes, SHA-256 `A0BEF3D637E0E120BFAD1B2D27B7C3C34990BB202D465A2FBE4EBB0D926D8BC9`; exactly three entries (EXE, Chinese guide, BUILD.txt), and the embedded EXE hash matches the release binary.|
| B11-04-A1/A2/A3 | PASS / PASS / PASS (offline preparation scope) | No unauthorized license/name/ownership migration; only local materials were generated without a Release; versioned Chinese and English documents are readable. Task remains `IMPLEMENTED_UNVERIFIED` because B11-02 native gates and any future publication authorization are separate prerequisites.|

Audit evidence is in ignored `evidence/local/`; it contains no runtime descriptor, credential, user content or process ID. This audit does not authorize making the repository public or publishing a Release.

## 2026-10-31 B05-02 local quota-source refactor

**Given** TeamSense collector source and synthetic Codex/vendor snapshots; **when** WinCraft projects Codex, DeepSeek, and MiniMax quota through its ordinary Provider and shared renderer; **then** the app does not call TeamSense, Codex rollout parsing remains bounded to quota events, vendor reads require explicit opt-in, and unknown/freshness/error states remain separate.

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `python -m unittest tests.test_quota_projection tests.test_codex_quota tests.test_codex_rollout_quota tests.test_provider_quota_sources -v` | PASS | 36 项 synthetic tests：额度投影、`token_count.rate_limits` 事件读取、超时/过期/未知、固定 DeepSeek/MiniMax GET、密钥 gate、重定向/响应上限、MiniMax 模型截断披露、last-good 标陈旧及 Provider 场景脱敏。没有真实 Codex 文件、供应商 key 或网络请求。|
| `python skills/wincraft-provider/scripts/verify.py` | PASS | 41 个 Provider Skill 源码、示例、测试、脚本和文档引用存在；引用清单已从 TeamSense 模块名改为本机 quota adapter。|
| `npm run check:local` | PASS | 退出码 0；UI 28 项、Rust workspace 149 项、Python 239 项（1 项 Windows symlink 能力跳过）、离线 schema/配置一致性与 strict Clippy 通过。|
| GitHub Actions commit `d95e396` / run `41189190278` | PASS | `dev` 远端 source job 执行 `npm run check:local` 完成；CI source validation 仍不替代真实账户、Tauri 原生窗口或人工像素验收。|
| `npm run codegraph:sync` / `npm run codegraph:status` | PASS | 索引同步后为 current：109 files、3,084 nodes、10,036 edges；数据库留在被忽略的 `.codegraph/`。|
| `python scripts/model_quota_headless_smoke.py` | PASS（真实 release Rust Host） | 退出码 0；隔离 loopback descriptor 创建成功，Provider 读取仅由本次测试生成的 `token_count` fixture、发布 quota 场景并在有界运行期后清理自己的世界。无真实文件、凭据或外网访问；测试后强制结束的仅是本次启动的 headless Host。临时 descriptor、fixture 与日志已清理。|
| TeamSense API、真实 Codex rollout/auth、DeepSeek/MiniMax live API | NOT_RUN | TeamSense 不再是 WinCraft 数据源；本轮只研究其本地实现。未读取真实用户 rollout/auth 文件、未设置/读取供应商 key、未发起真实上游请求。|
| Current native quota HUD pixels | NOT_RUN | Computer Use 重置后仍报 `Computer Use native pipe is unavailable: failed to connect native pipe: 系统找不到指定的文件。 (os error 2)`；renderer 场景由合成测试覆盖，不把协议 smoke 当作像素验收。|
| B05-02-A1/A2/A3/A4 | PASS / PARTIAL / PASS / PASS（synthetic/code） | A1/A3/A4 由合成投影、固定端点/opt-in 检查、敏感字段脱敏与 rollout 事件用例覆盖；A2 的时效字段和场景节点已验证，真实来源 freshness 与 native pixels 未验收，所以保持 PARTIAL。B05-02 仍为 `IMPLEMENTED_UNVERIFIED`。|

本地合成 smoke 没有把 descriptor、rollout 正文、凭据或来源值写入证据。汇总记录见 [`summary.json`](../../evidence/local/nextgen-2026-10-31/b05-02-quota-refactor-20261031/summary.json)；实现入口为 [`model_quota/`](../../examples/integrations/model_quota/)，本机 evidence 目录不跟踪提交。

## 2026-10-31 仓库公开与定向历史脱敏

**Given** 用户已授权修改 Git 历史并强推，且已将 `exomind-team/WinCraft` 由私有改为公开；**When** 在公开状态下复核工作树与全部可达 Git 历史中的凭据与个人路径标识，并对泄露字符串做定向替换后强制推送；**Then** 全部 114 个提交及其作者、提交信息与时间戳保持不变，只有含本机绝对路径的 2 个文件各改动 1 行，公开历史中不再残留凭据或本机身份标识。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `gh api repos/exomind-team/WinCraft` 可见性核对 | PASS | `exomind-team/WinCraft` 返回 `visibility: public`、`private: false`、默认分支 `dev`；`ARCJ137442/WinCraft` 重定向到同一仓库。公开动作由所有者执行，不是本轮 release 门的结果。|
| 公开前全历史凭据扫描 | PASS | 对 `git rev-list dev` 全部 114 个版本执行 `git grep -lIE` 匹配 `ghp_*`、`github_pat_*`、`AKIA*`、`sk-*`、`eyJ*`、`xox[baprs]-*` 等模式，命中 0 个版本。|
| 公开前全历史个人标识盘点 | PASS | 命中集中在本机用户目录路径（106 处）与本机交接下载目录（10 处），仅出现在 `docs/engineering/VALIDATION.md` 与 `docs/integrations/touchai-gap-matrix.md`；文档中的用户主目录已是占位写法，私人业务提供者名称在全历史 0 命中。|
| `git filter-repo --replace-text` 定向替换 | PASS | 保留全部 114 个提交、作者（ARCJ137442 / Argon）、提交信息与时间戳；重写后全历史个人路径与本机用户名命中数为 0。替换为 `<repo>`、`<touchai-checkout>`、`<handoff-dir>` 占位。|
| 重写差异范围核对 | PASS | 用重写前 bundle 对比新旧 HEAD：`git diff --stat` 显示仅 2 个文件、2 行改动，均为上述路径字符串，无其他内容差异；HEAD 树仍为 374 个跟踪文件。|
| 本地回归（`npm run test:ui` / `cargo test --workspace` / `npm run check:python`） | PASS | UI 30 项通过；Rust workspace 155 项通过、1 项 ignored；Python 238 项通过、1 项 skipped；Provider Skill 45 个引用存在。|
| `git push --force-with-lease=refs/heads/dev:b39f3f7...` | PASS | 远端 `dev` 由 `b39f3f7` 强制更新到 `96a66d3`；`gh api .../git/refs` 确认远端只保留 `refs/heads/dev` 一个引用，无 tag、无 release、无 PR。|
| GitHub Actions run `41209376248` | PASS | 公开后首次推送触发，耗时 5m50s，`npm run check:local` 步骤全绿（setup-python / rust-toolchain / npm ci / pip install / check:local）。CI 只验证源码，不替代原生窗口验收。|

重写前的本机备份为被忽略的 `target/wincraft-before-path-scrub.bundle`，仅用于本机恢复，不进入提交。历史中曾出现的私人业务提供者名称已在更早一次改写中移除，本次只处理路径标识。
