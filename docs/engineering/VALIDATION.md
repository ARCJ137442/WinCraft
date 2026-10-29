# 制作环境实际验证记录

本地开发与 CI 的统一命令、CodeGraph 使用方式及证据边界见 [开发规范与工具链](DEVELOPMENT_TOOLCHAIN.md)。该命令的 CI 结果不替代本文件记录的真实宿主、release 和人工验收。

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
| Obsidian Obsidian Workspace | PASS（此前本机 smoke） | 用户明确选择的只读仪表盘投影曾成功更新并应用到窗口；不在公共仓库记录 vault 标识、投影数量、任务标题或笔记内容 |
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
| 五课 Agent provider 教程 | PASS（release Tauri） | 五课在本地 release Tauri 宿主完整走完；动态插入、动作回执、主题应用/恢复、发现计数均使用合成数据。隐藏后从管理器恢复成功，教程世界结束后清理确认。|
| 教程运行与清理 | PASS（release Tauri） | release 宿主显示五课窗口；提供者结束后管理器回到 0 个世界，教程原生窗口消失。没有接触真实 Harness 或外心业务数据。|
| 焦点与待处理动作 | PASS（DOM） | pending 动作期间用 `aria-disabled` 保留键盘焦点，按组件阻止重复提交；回执只在原控件仍持有焦点时恢复，不把焦点从用户后来选中的控件抢回；Chromium smoke 回归通过。|
| 连接状态可访问性语义 | PASS（DOM） | `#status` 标记 `role=status`、`aria-live=polite`、`aria-atomic=true`；主窗口移除无用途的额外 Tab 停靠，滚动组件区仍可键盘聚焦。|
| Windows UIA/原生键盘/IME/读屏 | PARTIAL | 本轮通过当前 release 的 UIA 树验证教程五课、动态结构、回执、主题、窗口拖动及隐藏/管理器恢复；IME、真实键盘快捷键和读屏仍 NOT_RUN。|

shutdown 版在独立 Cargo target 中构建并以单实例运行。Computer Use 曾无法激活教程窗，未绕过该限制继续发送键鼠；人工 UIA/IME/读屏/五课验收仍待完成。

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
- TrafficMonitor、Obsidian Workspace 和 focus demo 的本机 provider smoke 曾观察到来源在线与窗口更新；公共记录省略 vault/source 标识、进程号、投影数量、真实标题与遥测值。
- TrafficMonitor x64 bridge 曾以本机源码重编并在隔离 staging copy 中验证；具体本机路径与实时遥测值留在忽略的本地证据。
- 本次环境：Windows 11 Pro 10.0.22000 x64、Python 3.11.4、Node v22.23.4、npm 11.19.0、Cargo 1.93.0、rustc 1.93.0。脱敏结果位于被忽略的 `evidence/local/nextgen-2026-10-26/lifecycle-tauri-lease-probe.json`。

## 2026-10-27 原生窗口动作与 Obsidian Workspace 联调

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
| Obsidian Obsidian Workspace 数据链路 | PASS（只读） | 用户选择的仪表盘只读投影曾持续更新并获得 native applied 回执；公共记录不含 vault 标识、投影数量、笔记内容或 runtime 信息。|
| Popup-Ask 并发配额子项 | PASS（unit/cross-process） | Windows 本机会话命名互斥体限制一个 Popup-Ask provider；同进程、独立子进程竞争和 busy-before-client/create 均有回归。server unit 还确认 manager scene 会列出 invite Popup world 且不改变其 writer/epoch；当前 release 的真实管理器可见性与不抢焦点仍 NOT_RUN，故 B03-02-A3 总体验收维持 NOT_RUN。|
| Popup provider 状态机与 headless wire | PASS（自动） | 22 项 Popup 专项测试覆盖成功 ACK 后单次销毁、重复 submit、取消/Escape/窗口关闭、超过 10 秒的整体等待、断线、ACK未知、busy 时错误退出与清理失败；Rust manager unit 确认 invite Popup world 出现在管理器 scene 且 writer/epoch 不变；真实 Rust headless host + 安装的 Popup-Ask skill 对合成请求验证 timeout/world.destroy 与并发 busy 拒绝，关闭后 descriptor count=0。首次 PowerShell 汇总器对空 stderr 调用 `.Contains` 而退出 1；后续 Python 结构化解析确认了所有结果字段，失败与复核均保存在本机证据。真实 Tauri Popup 的成功/取消、键盘/IME/读屏、管理器可见性及 native position reopen 仍 NOT_RUN。|
| 原生窗口动作人工点击 | NOT_RUN | 当前 release 的 Obsidian Workspace 标题声明 `obsidian/activate`；等待用户点击标题确认确实激活现有 Obsidian 窗口。后台 Python 进程直接调用 `SetForegroundWindow` 的诊断失败，故已移除提供者直接操作路径，改由接收用户点击的 Tauri 宿主执行。|
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
## 2026-10-27 交接包 planner/maintenance suite

当前契约检查会执行交接包 `docs/strategy/2026-10-26/tests` 的完整 unittest suite。单独运行结果为 **34 tests passed**，覆盖：full/optional/required/no-grant/ambiguous inventory、显式选择、过期/陈旧来源、未来时钟、重复身份、provider contract 版本、输入不变性、digest 稳定性、pack secret/path traversal、adapter 不执行、resolution plan schema，以及验收标准改变/显式 reset 后旧结果失效。

这组结果为 B06-02 和 B06-03-A1 的纯规划证据：inventory generation/digest/expiry 变化会使旧计划不可直接复用。它不证明 WinCraft runtime 已有计划提交器、资源账本或 rollback；B06-03 提交/回退仍未实现。

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

**Given** 两个互不重叠的 provider scope，分别由 TrafficMonitor bridge 与只读 Obsidian Obsidian Workspace 提供投影；**When** TrafficMonitor 的临时 x64 stage 被停止、其桥接快照转为过期；**Then** 仅 TrafficMonitor scope 更新为 stale，Obsidian Workspace scope 的投影保持不变，父 authority 仍独占窗口几何。

Core 新增可复现 seed 的 96 步 interleaving regression，交错执行两个 scope 的局部 props/data/CAS 写、越界 sibling 写与旧 revision 写。每步验证 owner scope generation、schema/value、reader grant generation、两边 namespace 与组件 props 独立；随后断开 scope A writer、用新会话/epoch 重加入、拒绝旧 lease，再删除 scope A 并验证其 owner slot 删除、scope B reader grant 清理。测试不依赖随机 crate，失败序列稳定可复现。

真实来源窄验收使用当前已授权的两条本地只读来源：TrafficMonitor bridge 提供由 `OnMonitorInfo` 持续生成的 snapshot；Obsidian CLI 对用户当前活动 vault 执行仓库内固定的 Obsidian Workspace dashboard 查询。组合 probe 把两个来源投影到分离的 `traffic` 与 `life` data namespace，并各自连接一个 scope writer。验收通过后只停止临时 stage copy 进行故障注入；原安装与配置不变，Obsidian 笔记/插件设置没有写入，临时 WinCraft world 已销毁。为了避免环境中原始 stage 携带的 `TrafficMonitor.sys`，`stage_demo.ps1` 现在从临时副本中排除该系统驱动；fresh configuration 未复制。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| `cargo test -p wincraft-core --test invariants deterministic_multiscope_interleavings_preserve_owners_and_sibling_business_state -- --nocapture` | PASS | seed 0x0b070403 的 96 步 interleaving 通过；跨 scope / stale revision 写不提交，disconnect 后 sibling scope data 与 subtree 不变，新 lease 取得更高 epoch，父删除清理 owner slot 和 reader grant。|
| `python -m unittest tests.test_multisource_composition tests.test_trafficmonitor_provider tests.test_trafficmonitor_staged_config -v` | PASS | 12 tests；组合 scene 只使用两组 namespaced bindings，Obsidian Workspace scope 使用 display-only title；来源错误 projection 仅在本 scope 变化并保留 last reading。|
| TrafficMonitor bridge x64 build + isolated stage | PASS | `build_bridge.ps1 -Architecture x64` 与 `stage_demo.ps1 -EnableBridgeItem` 成功；version 1.8.6.0，`ReuseConfiguration=false`，没有 optional driver 被复制。原先的 stale stage process 被停止，新临时 stage 在故障注入后重启并再次确认 snapshot fresh/advancing。|
| Obsidian Obsidian Workspace fixed CLI query | PASS | Obsidian CLI 在已打开的活动 vault 找到 Obsidian Workspace dashboard，返回结构通过 provider 解析。vault 名、笔记标题、事项与提醒内容不写入日志或 evidence。|
| `composition_probe.py` + real headless Rust WebSocket | PASS | 两个真实来源先写入分离 scope；停止 staged TrafficMonitor 后，仅 traffic scope 变 stale，Obsidian Workspace scope 数据完全相同；临时 world 销毁成功。未连接 Tauri renderer。|
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

## 2026-10-29 TeamSense 本机 Codex 数据源对照

**Given** TeamSense 既有 Codex 本机采集代码与其 App 用量静态调查；**When** 评估是否可替代 WinCraft 的 Codex App connector；**Then** 只复用已证明的只读字段和来源边界，不把用量采集器说成实时会话/消息采集器。

| 检查 | 状态 | 结论 |
|---|---|---|
| Codex rollout 与 state SQLite 采集实现 | PASS（源码审阅） | TeamSense `codex-usage-collector` 扫描 `sessions` / `archived_sessions` 的 JSONL，只解析 `event_msg.token_count`，用只读 `state_*.sqlite` 查询会话名、cwd、模型、source 与时间；游标状态本机持久化。它不读对话正文、Agent 输出或实时运行状态。 |
| Codex 账号额度采集 | PASS（源码/契约审阅） | 独立 `codex_quota` 模块从本机 `auth.json` 在内存中取 access token/account ID，读取 `/backend-api/wham/usage`，再核对请求期间账号是否切换；报告不含访问令牌。该私有 quota 路径与 rollout 历史分开，不等于 Codex App 分析图表 API。 |
| Codex Desktop 静态分析 | PARTIAL | TeamSense 调查文档记录了 App bundle 中的模块及若干相对 API 路径；没有实际请求验证个人账号图表端点、完整响应 Schema 或更新时间。现有本机采集器没有实现这些 analytics 路径。 |
| 能否替代 WinCraft 的会话卡片 | NO | TeamSense 现有本机采集器可供研究本机 thread metadata，但不提供状态与最后 Agent 输出；自身 SQL 也未取 `originator` 作为 App/CLI 来源区分。WinCraft 的真实 App snapshot bridge 仍需单独打通。 |

本次只读审阅了 TeamSense 源码、设计记录与本机 Codex 状态数据库字段；另对当前会话对应的 rollout 尾部做了 256 KiB 的结构检查，仅输出事件类别与文本长度，不展示或持久化消息正文。没有读取 `auth.json`、修改 TeamSense 或对 TeamSense 服务发起写入。TeamSense 的后续来源字段与 rollout 输出读取可作为 WinCraft 新适配器的设计参考，不能直接视为已接入或已验收。

### Codex Desktop 本机元数据回退场景

**Given** 本机 Codex `state_*.sqlite` 中唯一标记为 `originator=Codex Desktop` 的线程元数据，**When** Agent bridge 没有快照而本机数据库可读，**Then** 默认总览仍显示经脱敏的会话名与项目；没有受信状态时显示“状态未知”，只有 rollout 中精确匹配 session meta 的 `agent_message` 才可显示为最近 Agent 输出。Bridge 对同一 thread 提供权威字段时优先采用它；数据库缺字段、线程 ID 不匹配或 rollout 路径无法验证时失败关闭。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| Codex Desktop `state_*.sqlite` local-state adapter | PASS（合成与本机只读） | SQLite 以 read-only/query-only 打开；只选 `originator=Codex Desktop`、最近有界行、非 archived 记录。title/name 与 cwd 末级项目进入会话卡片，原始路径/ID不进入 scene；没有实时 App status 时明确为未知。本机查询因来源数量到达上限标 partial。 |
| rollout 尾部 Agent 输出 | PASS（合成） / PARTIAL（本机） | 只接受 sessions/archived_sessions 中以 `rollout-*.jsonl` 命名、且头部 `session_meta.payload.id` 与线程 UUID 匹配的文件；最多读取尾部 1 MiB，仅抽取 `event_msg.agent_message` 或 `task_complete.last_agent_message`，输出裁剪/脱敏并只保存在进程内。本机最近四条有界尾部未找到可呈现 Agent 消息，故真实输出仍不可验证。 |
| MCP bridge 与本机状态合并 | PASS（合成） | 同一 thread ID 不重复；connector 状态/项目/输出优先，本机可见但 connector 未覆盖的线程保留并使来源标为 partial。 |
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

## 2026-10-30 B08-03 按授权范围选择实时来源

**Given** Codex CLI 与 Claude Code 是本次获准读取的本机来源，Codex App connector 目标保持 `STALLED`，**When** Provider 使用 `--sources codex claude-code`，**Then** 只轮询这两个只读适配器；Codex App 本机状态库与 connector bridge 均不读取，界面明确标记“本轮未查询”，不显示旧 App 行或伪造空闲状态。

| 检查 | 状态 | 实际结果 |
|---|---|---|
| 未选择来源的拒绝与未知来源校验 | PASS（单测） | 定向测试验证空列表、重复项及未知 source ID 均在启动 CLI 适配器前失败关闭。|
| `codex` + `claude-code` source selection | PASS（单测） | 43 项 live-source/overview 定向测试通过；未选 Codex App 时不调用 Desktop SQLite/rollout fallback，不保留上一轮 App 行，UI 标记“本轮未查询”。|
| `npm run check:local` / CodeGraph / GitHub Actions | PASS | 本次工作树 28 项 Node UI、116 项 Rust workspace、159 项 Python 测试，契约与 27 个 Provider Skill 引用通过；CodeGraph 为 85 files、2,191 nodes、current。提交 `115cdc8` 的 GitHub Actions run [40914976329](https://github.com/exomind-team/WinCraft/actions/runs/40914976329) 在 Windows 上完整通过，耗时 7m59s。|
| 当前真实 Codex CLI / Claude 只读 adapter | PASS（本机只读） | 一次聚合快照显示 Codex CLI 来源 `online`、0 条可列会话；Claude `agents --json` 来源 `online`、2 条 `blocked` 后台 Agent。仅将来源健康和状态计数写入本机摘要，没有保存会话名称、项目、ID、输出或原始响应。|
| 当前 Tauri release global overview | PASS（协议/scene） | 当前 release 上以 `--sources codex claude-code` 运行实时只读 Provider：较早 60 秒 smoke 提交 4 次场景，最新 30 秒 smoke 提交 2 次；均退出 0 并走自身世界清理路径。Codex CLI 来源 `online`/0 条列表行，Claude 来源 `online`/2 条 `blocked` 后台 Agent；Codex App 标记 `not_requested` 且未读取。该 run 不提供像素截图或托盘验收。|
| 当前 release 像素验收 | NOT_RUN | Computer Use 窗口重新激活仍失败；不重试旧句柄/坐标，列表密度、真实点击和 DPI/多屏由人工按指南验收。|
