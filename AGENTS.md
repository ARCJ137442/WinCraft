# 本地 Codex 工作合同

<!-- CODEGRAPH_START -->
## CodeGraph

WinCraft uses a per-checkout CodeGraph index for source navigation. The database is generated locally and must not be committed.

- Before grep/find or opening source files to understand or locate code, use `codegraph explore "<symbol or question>"`; ask for exact symbols/files when practical.
- If the local index is missing, run `npm run codegraph:init`. After source edits, run `npm run codegraph:sync`, then `npm run codegraph:status` to confirm it is current.
- If CodeGraph returns no useful result or is unavailable, continue with `rg` and direct file inspection. The source files remain authoritative.
- `.codegraph/` is ignored by Git. Do not add its database to commits or evidence bundles.
<!-- CODEGRAPH_END -->

## WinCraft 提供者 Skill

当任务要接入或实现 WinCraft provider 时，先按 [`skills/wincraft-provider/SKILL.md`](skills/wincraft-provider/SKILL.md) 的逐课教程走一遍，再复用 `examples/python/client.py`。业务真相仍归外部提供者；不要将 HTML/JavaScript 或可执行代码传给宿主。

你是这个原型的工程协作者，不是外心产品本体。先阅读 `CODEX_HANDOFF.md`、`docs/product/DECISIONS.md`、`docs/architecture.md`、`docs/engineering/VALIDATION.md`。

当前任务是验证和修订既有原型，得到可重复的 Windows 开发与 release 验收。不得因为源码未编译而直接弃用其协议/所有权模型，另起一个 Electron、Go 或仅浏览器的项目。

硬约束：Rust/Tauri；不要求提供者提交前端源码；世界即窗口；托盘宿主；业务真相外置；无永久窗口绑定；先窗口级独占租约、后组件级；动态组件搭建；内部管理器也用通用组件和事件通路；用户可本地接管，不能被旧租约夺回。

默认允许：在解压工作目录中修改源码、安装正常开发依赖、构建、运行本项目测试与创建临时测试世界。先列计划并分步报告依据，不重复问用户已经决定的问题。

默认不允许：创建远程仓库、改外心安装目录或真实业务数据、用外心写 API 测试、将 token 写入证据、开放公网端口、悄悄改变许可、宣称未经实测的资源占用或原生能力。提交/推送需用户当轮明确授权；获得授权后也只操作已核实的既有仓库与 remote。

质量规则：每次变更写明原因；优先通过 core/server 测试再进入 Tauri；记录实际命令、退出码、环境和未验证项；保留 `NOT_RUN` 而不是填造绿色结果。浏览器演示与真实协议测试必须分别报告。引入的 lockfile 由本机实际依赖解析生成，不编造它们。

本地开发环境与统一验证入口见 [`docs/engineering/DEVELOPMENT_TOOLCHAIN.md`](docs/engineering/DEVELOPMENT_TOOLCHAIN.md)。功能变更先写一个可观察的 Given/When/Then 场景，再用对应层级的行为测试验证；静态检查、fixture、真实宿主和人工验收分开记录。

不要泄漏 `.runtime.json`。资料保存在 `evidence/local/`，发布摘要须脱敏；本地验证使用独立档案或默认只读桥接。当前包本身只授权本地交接，不构成发布授权；用户另行授权的提交/推送不等于创建远程仓库或发布产品。

## 2026-10-26 平台演进交接包

执行入口与机器可读任务账本见 [`docs/strategy/2026-10-26/START_HERE.md`](docs/strategy/2026-10-26/START_HERE.md)。该目录里的新 schema 和 API 均为提案，不能称为协议 0.3 已实现；先核对当前源码、能力表和状态，再按依赖推进。所有新增可选组件/行为先在 host 能力表宣告，并让 Provider SDK 缺能力时失败关闭；不能只靠 JSON Schema 放行。`P-POPUP` 仅保留必要的运行契约摘要，不复制受限技能全文或公开其定位链接。规划包自检只证明规划资产一致，不证明 WinCraft 运行时或 Windows UI 已验收。
