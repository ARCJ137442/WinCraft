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

- 当前可复现命令、环境、退出码与分层结果以 [`docs/engineering/VALIDATION.md`](docs/engineering/VALIDATION.md) 为准。2026-10-31 当前工作树 `npm run check:local` 退出码 0：28 项 UI、144 项 Rust workspace tests、199 项 Python tests（1 项 Windows symlink 用例跳过）、离线契约与 33 个 Provider Skill 引用检查通过。A4 新增回归保留快照中暂不可见的选中会话，并把撤销状态保持为明确未知；Host 撤销信号仍待接入。Provider 五课增加了有界运行时：当前 release 的 5 秒 synthetic smoke 已确认启动与自建世界清理，但课程交互和早先不确定世界的管理器清理仍待验。提交 [`69c3ec6`](https://github.com/exomind-team/WinCraft/commit/69c3ec668edb847153110bff352f4e508089ceab) 已推送至 `exomind-team/WinCraft/dev`，Windows Actions run [41109395539](https://github.com/exomind-team/WinCraft/actions/runs/41109395539) 通过；此前的 A4 提交 [`71d077c`](https://github.com/exomind-team/WinCraft/commit/71d077c5340ff2da59c7cc43d94ebdb5ddfa1f85) 的 Actions run [41105044150](https://github.com/exomind-team/WinCraft/actions/runs/41105044150) 与文档 checkpoint [`43b6ed9`](https://github.com/exomind-team/WinCraft/commit/43b6ed9538b75d11297cb554a034fc8dc0c9ec26) 的 run [41106633376](https://github.com/exomind-team/WinCraft/actions/runs/41106633376) 也通过。CI 只验证源码门禁，不替代原生 UI 验收。
- 阶段提交 [`a0366e1`](https://github.com/exomind-team/WinCraft/commit/a0366e1ecc9fb7e7eaaa1c23e14c161c400e56fd) 已推送到 `origin/dev`；对应 [Windows Actions run 40903194743](https://github.com/exomind-team/WinCraft/actions/runs/40903194743) 通过，耗时 7m02s。当前独立 release 的 Tauri-hosted `lease_probe.py` 返回 `PASS`、退出码 0；CI 和协议探针都不替代原生像素/人工验收。
- 2026-10-30 来源选择更新提交 [`115cdc8`](https://github.com/exomind-team/WinCraft/commit/115cdc8e2de20b1f5749819a4cc5816542c819c7) 已推送到 `origin/dev`；对应 [Windows Actions run 40914976329](https://github.com/exomind-team/WinCraft/actions/runs/40914976329) 通过，耗时 7m59s。此提交更新 Python Provider 和验证记录，Windows release EXE 保持不变。
- B06 阶段提交 [`e3e8df4`](https://github.com/exomind-team/WinCraft/commit/e3e8df4513841c22dd1ca7574e403991c9dbcb16) 的 [Actions run 40976867333](https://github.com/exomind-team/WinCraft/actions/runs/40976867333) 曾在 Clippy 1.99 新 lint 失败；修复提交 [`e3a4c4d`](https://github.com/exomind-team/WinCraft/commit/e3a4c4de4e345ac2230dec8f1aef6f62d049fc93) 已推送，并由 [Windows Actions run 40979104886](https://github.com/exomind-team/WinCraft/actions/runs/40979104886) 通过（11m26s）。这两个 CI run 均不替代 Manager 原生 UI 验收。
- B01-03 的 opt-in 0.4-preview endpoint-local provider inventory 已通过 loopback WebSocket/core/server/Python SDK 回归；0.3 `world.list` 不变，Host 不接受 grants、不会扫描其他 Host。
- 2026-10-29 的 release EXE 为旧版基线，12,429,312 bytes，SHA-256 `6FE0BD26E1CD848CA8B28DBA41EF03EDE586DFE1B91D19C28A46DAE1A56A8093`；它早于 B06-03 工作区改动。
- Earlier 2026-10-30 B06-03 release candidate from commit [`e3a4c4d`](https://github.com/exomind-team/WinCraft/commit/e3a4c4de4e345ac2230dec8f1aef6f62d049fc93) built with SHA-256 `0FCC6BB2FD9E6FA462B1A04972180700995345F4B0F1BDA4C57B9749D2693E5A`; its manager pixel state was not observed then. The newer local B04-03 candidate is described below.
- B06-03 的 Rust Host/manager 运行时导入、显式授权与回退已实现；2026-10-31 重跑 `cargo test -p wincraft-server pack_import --no-fail-fast` 16 项通过，覆盖 generation 变化、取消、授权/re-preview、部分失败与账本回退。`npm run check:local`、capability 回归、真实 Tauri Host 的只读 hello/capability smoke 和 Windows Actions run 40979104886（11m26s）通过；这些不等于 Manager UI 通过。当前 release UI 的预览、授权重规划、应用、Provider 回执、取消与回退点击仍 NOT_RUN。
- B06-04 的 full/optional-missing/required-missing/no-grant 合成 inventory、workday `.wcp` 与双环境中文验收步骤已记录。2026-10-31 重新导出的 1,109-byte `.wcp` 只有 `pack.json` 与声明的 blueprint；扫描未发现凭据键、绝对用户路径、runtime/session 标记或额外条目，adapter 为 null；导出器专项测试 10 通过、1 项 symlink 用例因 Windows 能力跳过。两个独立用户环境的 Provider 重新授权仍未实测，B06-04-A1/A2/A3 保持 PARTIAL。
- B08-01 活动聚合器与 B09-01 设备收件箱用合成 fixture 完成 L1-L2 验证。B08-02 按 2026-10-30 用户澄清改为本机进程 + 磁盘数据：Codex App 只读 Desktop-originator state DB 与 UUID 匹配 rollout，Claude Code 读取项目 JSONL/已知子 Agent 文件；不与 Codex App 通信、不运行 Claude 状态 CLI、不为采集启动目标进程。进程在线、数据可读性和读取年龄分开展示；本地文件没有权威逐会话状态时保持 `unknown`。2026-10-31 当前标准 release 的只读 `live_provider.py --sources codex codex-app claude-code` 运行 11 秒、提交 3 次真实本机来源快照并清理自己的临时世界：Codex CLI online/0 个可列状态，Codex App online/128 条状态未知，Claude Code offline/128 条历史状态未知；没有启动任何 Harness，也没有保存会话内容。B08-02-A5 保持 PARTIAL，因为 freshness 像素仍未观察；Codex App UUID-only 深链子目标仍 STALLED/NOT_RUN，B08-02 整体仍 IN_PROGRESS。
- B08-03-A1 五类来源入口/本机版本/未知边界矩阵已 PASS；Codex CLI/Claude Code 有只读 smoke，OpenCode/DSH/omp adapters 仍 `NOT_RUN`。单窗口 Global Agent Overview 的 A6/A7 有合成 release 证据；当前 release 的 live Provider 在 2026-10-31 用 `--sources codex codex-app claude-code` 提交 3 次真实本机快照并清理自身世界，摘要为 Codex CLI online/0 个可列状态、Codex App online/128 条 unknown、Claude Code offline/128 条 unknown；没有保存会话内容。A2 现为 L2 `PASS`：`scoped_live_sources.py` 启动两个独立 OS Provider 进程，分别用真实 Codex CLI/Claude Code 本机来源写入互不相交的 source scopes，租约重叠 19.91 秒并确认清理；汇总证据未保存会话内容或进程 ID。A3 仍 `PARTIAL`：Hub/WebSocket 回归通过 owner-only 路由、当前 scoped lease 回执、撤销 fencing 与 stable 0.3 拒绝，但原生按钮尚未点击。A4 仍 `PARTIAL`：选中会话从快照消失时现保留显示身份、显示来源 freshness 并标记撤销未知，恢复后回到实时详情；可信 Host scope 撤销信号尚未端到端接入。A5 为 `PASS`（14 项测试、既有有界 release UI 证据及当前 release 场景/清理 smoke）；A8 仍 `PARTIAL`。
- 2026-10-31 重建的 `target/release/wincraft-desktop.exe` 为 13,572,608 bytes，SHA-256 `0E5ECCAD24E04653C3E8F878CF96C370E3A74F68AC4EFE742C70EA10284422C7`；以 `--open-manager` 启动后，`scope_interaction_demo.py --duration-seconds 1` 通过真实 Tauri Host 的 capability/创建/scope writer/自清理 smoke。未点击动作控件；像素与原生 action ack 仍 NOT_RUN。
- B05-02 TeamSense：只读 Agent API 已在本地源码/文档确认，`GET /v1/integrations/models` 受 `data:read` token 保护，返回缓存的 DeepSeek 余额、MiniMax 分模型/周期额度、Sub2API 管理快照及 freshness。新增 [`examples/integrations/model_quota/`](examples/integrations/model_quota/) Provider 只消费该固定 GET，拒绝远端明文 HTTP/重定向，并且只保留脱敏后的展示投影。Codex 不在该 endpoint，仍显示 unknown；响应没有账户标识，因此不能声称按账户归属验收。合成回归和标准 Tauri Host 场景已通过；真实 TeamSense token/API 与窗口像素仍 NOT_RUN，不调用 `/api/codex/usage`、刷新或供应商 API。
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
