# WinCraft 原型工程交接

版本：0.1.0-alpha.1。目标平台：Windows 优先。正式名称尚未冻结。

## 交接目标

从**已经写好的源码**得到能够在用户 Windows 机器上真实运行并复验的开发版与 release 原型。第一目标不是扩组件市场或桌宠，而是让不懂前端的外部程序通过协议使用原生窗口，且所有权、断线、动作与救援都可靠。

最短入口是根目录 `CODEX_PROMPT.md`。产品约束见 `docs/product/DECISIONS.md`，协议细节见 `docs/protocol.md`，事实基线见 `docs/engineering/VALIDATION.md`。

## 初始交接状态，不能误读

| 对象 | 交接时状态 |
|---|---|
| TypeScript 共享 renderer | 严格构建和 Node 测试通过 |
| 浏览器交互 | Chromium 中使用实际编译模块 + 模拟提供者通过部分 DOM 测试 |
| Rust 内核、Axum 服务、Tauri 适配 | 有实现与测试源码；没有 Rust 编译或原生执行证据 |
| Python 提供者 | 语法检查通过；真实连接待运行 |
| 外心桥接 | 已核对源码接口；默认只读；真实 RT 未连接 |
| 依赖锁定 | 尚无 Cargo.lock/package-lock.json，必须实际解析生成 |
| 可执行文件 | 本包不含已构建 Windows EXE，不声称可直接安装 |

22 个 Rust 测试定义不等于 22 个通过；JSON schema 检查不等于服务实际按 schema 行为；截图不等于 Tauri 窗口通过。

## 当前验证与仓库状态（2026-10-31）

- 当前可复现命令、环境、退出码与分层结果以 [`docs/engineering/VALIDATION.md`](docs/engineering/VALIDATION.md) 为准。2026-10-31 最新 `npm run check:local` 退出码 0：28 项 UI、149 项 Rust workspace、220 项 Python（1 项 Windows symlink 能力跳过）、Clippy、离线契约和 33 个 Provider Skill 引用通过。`0.4-preview.1` 增加 metadata-only `scope.status`，真实 headless Rust Host 已验证两个来源 writer 的 `online → stale` 与 Codex scope `revoked`；live overview 现会跨 Codex CLI、Codex App、Claude Code 来源切换保留各自 selected detail identity/page，missing tombstone 跨切换仍保持 freshness 与 unknown；本机来源没有逐会话权威撤销信号，A4 仍 PARTIAL。B11-03 Linux WSL2 下 Tauri debug ELF、147 项 workspace 测试与严格 Clippy 通过，Linux GUI、X11/Wayland 行为与 macOS 仍 NOT_RUN，能力矩阵见 [`docs/platforms/capability-matrix.md`](docs/platforms/capability-matrix.md)。最新 Windows release 已从提交 `c8368023fba08ef620c56bb1a436e1c5e2d87ed6` 构建，Actions run [41140899841](https://github.com/exomind-team/WinCraft/actions/runs/41140899841) 通过（11m43s）；该自动门禁不替代原生 UI 验收。此前 scope-status 检查点 commit `a78b3c9d4e9e19be7045faad4920d060f3c990c1` / Actions [41123291608](https://github.com/exomind-team/WinCraft/actions/runs/41123291608)、Provider 视图状态提交 `0696cbeb9b3ef69cb9c6a9b43901fae6e922ea7b` / Actions [41128511607](https://github.com/exomind-team/WinCraft/actions/runs/41128511607)，以及 Codex App detail restoration 回归 `c3928722dc3b039c49a40a3f53e6171d003c188b` / Actions [41132589475](https://github.com/exomind-team/WinCraft/actions/runs/41132589475) 均通过。Python 示例变更不打包进 EXE。
- B11-03 当前记录为 `IMPLEMENTED_UNVERIFIED`：Linux WSL2 Tauri debug ELF、147 项 workspace tests 和严格 Clippy 已通过；Windows commit `c836802` 的 Actions run `41140899841` 通过。最新 Windows EXE 与中文验收指南已打入本机忽略包 [`WinCraft-alpha1-acceptance-delivery-b11-03.zip`](evidence/local/nextgen-2026-10-31/WinCraft-alpha1-acceptance-delivery-b11-03.zip)；Linux GUI、X11/Wayland 和 macOS 原生验收仍 `NOT_RUN`。
- 阶段提交 [`a0366e1`](https://github.com/exomind-team/WinCraft/commit/a0366e1ecc9fb7e7eaaa1c23e14c161c400e56fd) 已推送到 `origin/dev`；对应 [Windows Actions run 40903194743](https://github.com/exomind-team/WinCraft/actions/runs/40903194743) 通过，耗时 7m02s。当前独立 release 的 Tauri-hosted `lease_probe.py` 返回 `PASS`、退出码 0；CI 和协议探针都不替代原生像素/人工验收。
- 2026-10-30 来源选择更新提交 [`115cdc8`](https://github.com/exomind-team/WinCraft/commit/115cdc8e2de20b1f5749819a4cc5816542c819c7) 已推送到 `origin/dev`；对应 [Windows Actions run 40914976329](https://github.com/exomind-team/WinCraft/actions/runs/40914976329) 通过，耗时 7m59s。此提交更新 Python Provider 和验证记录，Windows release EXE 保持不变。
- B06 阶段提交 [`e3e8df4`](https://github.com/exomind-team/WinCraft/commit/e3e8df4513841c22dd1ca7574e403991c9dbcb16) 的 [Actions run 40976867333](https://github.com/exomind-team/WinCraft/actions/runs/40976867333) 曾在 Clippy 1.99 新 lint 失败；修复提交 [`e3a4c4d`](https://github.com/exomind-team/WinCraft/commit/e3a4c4de4e345ac2230dec8f1aef6f62d049fc93) 已推送，并由 [Windows Actions run 40979104886](https://github.com/exomind-team/WinCraft/actions/runs/40979104886) 通过（11m26s）。这两个 CI run 均不替代 Manager 原生 UI 验收。
- B01-03 的 opt-in 0.4-preview endpoint-local provider inventory 已通过 loopback WebSocket/core/server/Python SDK 回归；0.3 `world.list` 不变，Host 不接受 grants、不会扫描其他 Host。
- 2026-10-29 的 release EXE 为旧版基线，12,429,312 bytes，SHA-256 `6FE0BD26E1CD848CA8B28DBA41EF03EDE586DFE1B91D19C28A46DAE1A56A8093`；它早于 B06-03 工作区改动。
- Earlier 2026-10-30 B06-03 release candidate from commit [`e3a4c4d`](https://github.com/exomind-team/WinCraft/commit/e3a4c4de4e345ac2230dec8f1aef6f62d049fc93) built with SHA-256 `0FCC6BB2FD9E6FA462B1A04972180700995345F4B0F1BDA4C57B9749D2693E5A`; its manager pixel state was not observed then. The newer local B04-03 candidate is described below.
- B06-03 的 Host 导入、显式授权与回退已实现；当前 server 56 项测试及全量 workspace/UI/Python 门禁通过。ManagerProvider 回归覆盖授权重规划、Host 拒绝 generation 过期授权并清除旧预览，以及旧 grant 动作不清除较新有效预览。当前 Windows Tauri release `target/release/wincraft-desktop.exe` 来自提交 [`9073b3b`](https://github.com/exomind-team/WinCraft/commit/9073b3bd77e439e95c6452967a33416d31f23a11)，13,600,256 bytes，SHA-256 `7E910E01057DADB17991B00D2A51CE63419628F818C35C06C1EE3D0C3179D691`；最终 release headless Rust Host 和独立 Tauri release Host 均通过 Python `lease_probe.py` 41 项协议检查。修复提交 `9073b3b` 和验收文档提交 `8bee25d` 已推送；Windows Actions run [41154964442](https://github.com/exomind-team/WinCraft/actions/runs/41154964442) 通过（12m32s）。Manager 原生 UI 点击、授权/重规划画面、Provider 回执与回退像素仍 NOT_RUN；旧提交 `17ddee4` 的 Actions run 41151206263 早于本次修复。重复构建 hash 变化和 CI 详情见验证记录。
- B11-01 增加 Windows WMI process-tree sampler 和 synthetic Provider latency probe。context-complete Tauri release 的 61.203 秒采样记录到 8 个峰值进程、580,329,472-byte working set、394,821,632-byte private memory、4,262 handles 和 357 threads；p95 machine CPU 1.489%。powercfg 前后均为 Turbo，WMI 未报告电池或 ACPI 电源源；未做 sleep/wake。两次 paced 50/200/100/20 RPC runs 的 p95 尾部有波动，最大观察到 create 36.156 ms、destroy 41.855 ms、snapshot 26.206 ms、raw data.replace 35.827 ms、reconnect+join 3.763 ms。采样工具 commit `31d7675` 的 Windows Actions run [41161166248](https://github.com/exomind-team/WinCraft/actions/runs/41161166248) 通过（10m24s，220 Python/1 skip）；仅是本机短时合成基线，长期泄漏、sleep/wake 和阈值 ADR 仍未验收，详见 [`docs/performance.md`](docs/performance.md)。
- B06-04 的 full/optional-missing/required-missing/no-grant 合成 inventory、workday `.wcp` 与双环境中文验收步骤已记录。2026-10-31 重新导出的 1,109-byte `.wcp` 只有 `pack.json` 与声明的 blueprint；扫描未发现凭据键、绝对用户路径、runtime/session 标记或额外条目，adapter 为 null；导出器专项测试 10 通过、1 项 symlink 用例因 Windows 能力跳过。两个独立用户环境的 Provider 重新授权仍未实测，B06-04-A1/A2/A3 保持 PARTIAL。
- B08-01 活动聚合器与 B09-01 设备收件箱用合成 fixture 完成 L1-L2 验证。B08-02 按 2026-10-30 用户澄清改为本机进程 + 磁盘数据：Codex App 只读 Desktop-originator state DB 与 UUID 匹配 rollout，Claude Code 读取项目 JSONL/已知子 Agent 文件；不与 Codex App 通信、不运行 Claude 状态 CLI、不为采集启动目标进程。进程在线、数据可读性和读取年龄分开展示；本地文件没有权威逐会话状态时保持 `unknown`。2026-10-31 当前标准 release 的只读 `live_provider.py --sources codex codex-app claude-code` 运行 11 秒、提交 3 次真实本机来源快照并清理自己的临时世界：Codex CLI online/0 个可列状态，Codex App online/128 条状态未知，Claude Code offline/128 条历史状态未知；没有启动任何 Harness，也没有保存会话内容。B08-02-A5 保持 PARTIAL，因为 freshness 像素仍未观察；Codex App UUID-only 深链子目标仍 STALLED/NOT_RUN，B08-02 整体仍 IN_PROGRESS。
- B08-03-A1 五类来源入口/本机版本/未知边界矩阵已 PASS；Codex CLI/Claude Code 有只读 smoke，OpenCode/DSH/omp adapters 仍 `NOT_RUN`。当前 live Provider 已实测三个本机来源更新同一总览世界；A2 为 L2 `PASS`，两个独立 OS Provider process 写入不相交 scope 并确认清理。A3 Hub/WebSocket owner 路由、回执与撤销 fencing 通过，但原生按钮尚未点击。A4 已补 metadata-only Host scope 生命周期状态与真实 `online/stale/revoked` smoke；所选会话缺失仍只能标记撤销未知，不能由 component scope 状态推断，故保持 `PARTIAL`。A5 为 `PASS`（14 项测试、既有有界 release UI 证据及当前场景/清理 smoke）；A8 仍 `PARTIAL`。
- 2026-10-31 当前 `target/release/wincraft-desktop.exe` 由 `npm run desktop:build` 退出码 0 构建，13,595,648 bytes，SHA-256 `64458EA768A36FE012230EA34D0E37936FB1ACF1FA74C1A49802C8D456BD7314`。该构建包含当前工作树 scope-status Host 变更；旧 QA 宿主已按用户授权关闭。没有做本轮 Tauri UI 像素复验；真实 headless Rust Host 生命周期 smoke 与 `npm run check:local` 结果见验证矩阵。
- B05-02 模型额度 HUD：TeamSense 使用受 data:read 保护的固定缓存 GET /v1/integrations/models；Codex 有独立的默认关闭本机凭据适配器，必须显式传 --codex-quota 才会有界解析 auth.json 并仅使用必要字段请求未公开稳定契约的固定 HTTPS GET。两个来源不合并账户、窗口、单位或新鲜度；Codex 账号切换/身份无法确认会清除旧读数。合成回归与新编译的真实 headless Rust Host 场景已通过，真实 TeamSense/Codex 请求、桌面像素与用户账户状态仍 NOT_RUN；不使用管理员/dashboard/刷新/供应商写接口。私有仓库 Actions run 41149432751 已通过（12m45s）。详情与可复现命令见 examples/integrations/model_quota/README.md 和 docs/engineering/VALIDATION.md。
- B04-03 本机实现已通过 `npm run check:local` 与 `desktop:build`；commit `309af17` 的 Windows Actions run `41024348330`、随后 `c36e4af` 的 run `41026654580` 均通过。早先运行的 `target/release` EXE（SHA-256 `5E6061827A3B4527BFEEA1307A5945A8EAB8976C8BDC47A86BFE2F4B654B6F8F`）早于快捷键实现提交 `4bc3e81`，已停止。隔离候选曾以 41 项真实 `lease_probe.py` 通过；2026-10-30 随后从当时的 HEAD 重建标准 `target/release/wincraft-desktop.exe`（13,559,808 bytes，SHA-256 `C949FC2359B5D36DA9FF3C2CAD395D07914699D13DF9130A985CC3160070BA25`），并以 `--open-manager` 运行、通过 41 项真实 Tauri-hosted `lease_probe.py`；该候选已于 2026-10-31 停止并由下方当前 release 替换。Computer Use 原生管道当前不可用，所以热键启用、按键触发、冲突/撤销与 IME 行为仍 `NOT_RUN`；B04-03 保持 `IMPLEMENTED_UNVERIFIED`。本轮完整本地 `npm run check:local` 退出码 0；产物与命令证据见 [`docs/engineering/VALIDATION.md`](docs/engineering/VALIDATION.md) 与本机忽略证据。
- B04-04 已对用户指定的 TouchAI checkout 做只读源码核对：`cdc9b399d0ea6813be321b6a87e39d3532d1a7da`，GPL-3.0-or-later，Tauri 2/Vue 3；确认 Alt+Space→搜索输入→TaskCenter 请求/流式→启动 AbortController 或运行中 cancelTask。未启动 TouchAI、未读写其数据库、未复制代码；A2/A3 PASS，真实 workflow A1 NOT_RUN，任务仍 BLOCKED，详见 [TouchAI 差异矩阵](docs/integrations/touchai-gap-matrix.md)。
- B09-02 `adb devices -l` 当前发现 1 台在线设备与 1 台离线设备；未枚举应用或读取通知。没有用户选定的 app/source 和通知权限，任务状态为 `BLOCKED`。
- Python 提供者已统一按真实 wire envelope 读取顶层 `world.deleted.world_id`；Tauri-hosted `lease_probe.py` 最终 41 项通过，包含删除事件送达原成员检查。
- 本地 Tauri release 和用户人工验收状态按验证矩阵记录；浏览器预览、合成 provider、真实协议和原生 UI 证据不可互相替代。
- 当前主仓库是 GitHub `exomind-team/WinCraft`，默认分支 `dev`，远端为私有仓库。之前的 `ARCJ137442/WinCraft` 公开历史已转入该仓库；可达历史扫描没有发现凭据命中，但一个旧提交曾包含本机绝对目录。重新公开前必须清理或替换该历史并再次扫描。
- 工作树的 `evidence/local/` 被忽略且可能含过期 runtime 描述文件和机器路径；这些内容不是可提交证据。当前扫描发现 5 个旧测试描述文件命中凭据规则，不能打包或分享。原始日志继续保留在本地。
- 核心与独立 Provider/应用按仓库边界演进，子项目名统一 `wincraft-XXX`；实际业务世界状态不入库，只能提交审查过的无业务数据蓝图与合成样例。

## 必须保留的设计不变量

1. 同一世界最多一个活跃写租约。所有远程写入验证会话、lease ID、epoch、单调时钟到期和预期版本。
2. 读取是权限受限的不可变快照，不是 Rust `&T` 与 `&mut T` 的跨进程复制。发现只返回摘要，场景读取仍需加入。
3. 批量组件 patch 全部成功或全部失败；不支持的组件/属性明确报错。
4. 业务真相不落入宿主数据库；运行中暂存、输入草稿、缓存和会话状态不冒充业务记录。
5. 正常动作回到当前写者；发送成功不是业务成功。动作有 pending/ok/error/timeout；拒绝来自旧 revision 的点击。
6. 窗口配置接受与原生属性应用分开；原生失败显示为错误，不谎报已应用。
7. 人类几何模式不被普通 provider 坐标更新覆盖；本地管理器接管设置 hold，需要显式解除，不能下一次 join 就夺回。
8. 一个窗口一个共享 renderer 实例，不按提供者另建 WebView；管理与设置也是组件声明。
9. 没有固定端口、没有匿名档案 fallback、没有跨重启永久绑定。
10. 保留 ExoMind 来源许可、固定 SHA 和修改说明。

## 实施顺序与命令

### A. 静态基线和依赖

使用 Node 22、Python 3.11+、当前可用的 Rust stable。先确认工作目录，不覆盖其他同名项目。保存初始文件清单与 SHA256；`MANIFEST.sha256` 是交接快照，不要求修改后仍匹配。

```powershell
npm ci
python -m pip install -r requirements-dev.txt -r examples/python/requirements.txt
npm run check:local
```

`check:local` 覆盖 UI 行为与离线契约、Rust workspace（包括 Tauri crate）的 fmt/check/test/clippy，以及 Python provider 单测和 Skill 校验。锁文件必须来自真实依赖解析；常规 checkout 使用 `npm ci`，调整依赖时才运行 `npm install` 并审阅 lockfile 差异。分层命令和 CI 边界见 [`docs/engineering/DEVELOPMENT_TOOLCHAIN.md`](docs/engineering/DEVELOPMENT_TOOLCHAIN.md)。

### B. 无界面真实协议

终端 A：

```powershell
cargo run -p wincraft-server --bin wincraft-headless
```

终端 B（复制实际输出的描述文件路径）：

```powershell
python examples/python/lease_probe.py --runtime "<实际描述文件>"
python examples/python/focus_demo.py --runtime "<实际描述文件>"
```

headless 不画窗口；它只证明真实 Rust 状态机和 WebSocket 行为。给 `lease_probe.py` 扩充断网/超时场景时，使用不同连接，不模拟成同一 session。不要让客户端提供 host 时钟。

### C. Windows 桌面

按 Tauri 官方 prerequisites 安装 Windows C++ 工具链与 WebView2；不要安装 Electron。

```powershell
npm run desktop:dev
```

预期：主进程常驻托盘，无默认主窗口；托盘打开“世界管理器”。为本机自动化联调，构建后的 EXE 也接受显式 `--open-manager` 参数，启动时打开管理器；不带参数仍保持 tray-only。管理器显示实际描述文件路径。启动 Python 示例，检查是否出现真正可置顶、可移动的窗口，而非浏览器卡片。

检查 Tauri `beforeDevCommand` / `beforeBuildCommand` 工作目录、应用自定义命令 ACL、动态 `world-*` labels 的 capability、`WebviewWindow` 调用者注入、`Image::from_bytes`、tray 回调和原生窗口 setter 的精确版本签名。这里是优先定位区，不是预先断言必然有错误。

### D. 独立 release

```powershell
npm run desktop:build
```

实际产物通常位于 Cargo target 的 release 子目录，但必须先确认真实路径再报告。关闭仅用于本项目的 dev 实例后，直接启动生成 EXE；不要通过 Vite 代理声称 release 成功。也要测试两个宿主实例同时运行：不同 host_id、端口、描述文件，不互删对方令牌文件。

### E. 外心只读集成

```powershell
python examples/python/exomind_readonly.py --runtime "<WinCraft 实际描述文件>" --exomind "http://127.0.0.1:<实际 RT 端口>" --profile "<明确档案 ID>"
```

详细边界见 `docs/integration-exomind.md`。已有源码支持 `GET /timeblocks/active?user_id=...`，但真实返回结构/鉴权/运行端口都需要当前现场核验。不得把 404 直接当成“用户没有时间块”；它也可能是端点不匹配。

## 代码地图与优先审查点

| 入口 | 最该看什么 |
|---|---|
| core/model.rs、engine.rs | 写租约、防旧写 fencing、revision/sequence 区分、operator hold |
| core/scene.rs | 克隆候选再提交、ID 唯一、移入自身拒绝、资源上限 |
| server/hub.rs | 所有外部 method 与内部 provider 共用 dispatch；锁不得跨 await |
| server/transport.rs | Upgrade 前鉴权、Origin 拒绝、握手/限流/断线处理、描述文件权限 |
| server/self_provider.rs | 内部管理器不能暗建第二套 UI；受信本地管理权限与普通 lease 区分 |
| desktop/src-tauri/src/windows.rs | UI 线程与回调、DPI 坐标、关闭拦截、应用回执、拖动回声抑制 |
| desktop/src/main.ts、renderer.ts | 先订阅后快照、sequence fencing、键控节点、IME、原生/预览分离 |
| Python client.py | 并发请求回包匹配、心跳、超时不盲重试、lease epoch、host_id 校验 |

已知工程债：50ms 全快照扫描与完整快照通知不是最终性能架构；内核锁中克隆场景；组件级租约暂缺；没有 origin 白名单/TLS 和生产级跨用户鉴权；Windows descriptor ACL、多屏/DPI、click-through 救援、IME 原生路径和休眠恢复仍需专门验收。它们不应被隐瞒，也不要求本地 Codex 一口气实现所有后续愿景。

## 验收、回滚与交付

执行 `docs/engineering/ACCEPTANCE.md` 的分层用例。某层失败时保留可独立完成的其他层结果，不能把“不具备 Windows 环境”写成全部成功。修改后重新运行与变更相关的回归。

不要改用户外心的安装/数据库；试验世界可由托盘关闭或退出本宿主清理。需要重置时关闭本项目的宿主，只清理本项目生成的运行描述文件。不要全盘删除 AppData、不要结束全部 WebView2 进程。

本地最终报告必须包含：环境及依赖版本、真实命令/退出码、修复摘要、三层测试矩阵、脱敏截图、实际构建路径、已知问题。记录保存在 `evidence/local/`；源证据不可覆盖。未明确授权时，不远程发布或推送。
