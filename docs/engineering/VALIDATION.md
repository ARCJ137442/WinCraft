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
| B01-03 世界发现 | IMPLEMENTED_UNVERIFIED | 当前 0.3 `world.list` 仅列当前成员及非系统 open_authenticated worlds；invite-only 未加入项隐藏，open-world listing 仍需 `world.join` 才能读取。provider type/version/capability/freshness registry 仍为 proposal |
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
| B01-03 多来源 inventory | IMPLEMENTED_UNVERIFIED | Provider 类型、版本、能力 grants、新鲜度 TTL 与多 endpoint registry 仍是策略包 draft；未伪称现有 `world.list` 已完成该独立 inventory。|
| 原生 manager language toggle | PASS（UIA tree） | 单实例 Tauri manager 从中文切换为英文并在 UIA 中观察到标题/动作文本更新，之后观察到中文已恢复。|
| 教程隐藏恢复/Popup键盘/IME/读屏 | NOT_RUN | Computer Use 对唯一教程窗口执行首次点击与一次重新激活仍失败；没有再尝试其它 UI 输入通道。manager、tutorial UIA 树的控件名已读取，截图回传错窗后丢弃且未保存。|

此前的 manager/provider 进程已按所属项目范围清理。Computer Use 恢复失败后没有再发送键鼠输入。UIA/IME/屏幕阅读器和五课完整交互仍待人工验收。

## B02-03 / B02-04 本轮增量（2026-10-26）

| 事项 | 状态 | 证据与边界 |
|---|---|---|
| 五课 Agent provider 教程 | IMPLEMENTED_UNVERIFIED | `provider_tutorial.py` 只调用公共 client/protocol；五课 fixture 全部通过本地 scene schema，发现课只保留数量与加入策略计数，不保存世界 ID/标题或 scene。普通 provider 实际创建 `system=false` 且 `join_policy=invite` 的世界；未请求 operator 能力。|
| 教程运行与清理 | PASS（headless） | 真实 Rust host 接受连接、`theme_tokens` 能力门和首个 scene；结束时输出 cleanup confirmed；之后仅按合成教程标题计数，结果为 0。 headless native 状态不可用，因此未验隐藏/恢复像素行为。|
| 焦点与待处理动作 | PASS（DOM） | pending 动作期间用 `aria-disabled` 保留键盘焦点，按组件阻止重复提交；回执只在原控件仍持有焦点时恢复，不把焦点从用户后来选中的控件抢回；Chromium smoke 回归通过。|
| 连接状态可访问性语义 | PASS（DOM） | `#status` 标记 `role=status`、`aria-live=polite`、`aria-atomic=true`；主窗口移除无用途的额外 Tab 停靠，滚动组件区仍可键盘聚焦。|
| Windows UIA/原生键盘/IME/读屏 | PARTIAL | manager 与 synthetic tutorial 的 UIA 树已读；manager 语言切换可用。Computer Use 对 tutorial 的索引点击报 `coordinate input geometry is unavailable`，重新选择后激活报 `failed to activate captured window`；没有继续键鼠操作，IME/读屏和完整课程保持 NOT_RUN。|

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

CI 回顾：GitHub Actions 在 2026-10-28 连续 9 次于 `npm run check:local` 失败，日志共同显示 Windows 默认 `cp1252` 读取 UTF-8 夹具，以及 LF/CRLF checkout 使翻译源哈希误报；提交 `5e5f7e9` 显式固定 UTF-8 并按文本规范化换行，随后 Actions 更新到 Node 24 运行时。最新已推送运行 `40801981651`、`40726526250` 均成功。B07-03 当前工作区改动尚未进入远端 CI；推送后必须记录对应运行结论。

脱敏本地证据见 `evidence/local/nextgen-2026-10-29/b07-03-validation.json`。Headless 探针使用合成标识与临时 world；descriptor 仅由 Python client 为连接读取，临时文件在探针后删除，没有被复制或写入证据。回滚边界：移除 preview state slot 方法、capability、SDK helper 和 fixture 即可关闭高级共享；稳定 0.3 与已有 scope 结构能力不变。
