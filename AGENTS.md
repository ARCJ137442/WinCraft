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

硬约束：Rust/Tauri；不要求提供者提交前端源码；世界即窗口；托盘宿主；悬浮窗默认置顶且提供者可配置；业务真相外置；无永久窗口绑定；先窗口级独占租约、后组件级；动态组件搭建；内部管理器也用通用组件和事件通路；用户可本地接管，不能被旧租约夺回。

本机 Harness 数据规则：Codex App 与 Claude Code 的来源在线状态只通过宿主读取 OS 进程元数据判断，详情只读其明确数据目录；不得为采集而启动 Codex App/Claude CLI 或调用 App/MCP connector。Codex CLI 的 app-server 状态库适配是独立来源，固定 `useStateDbOnly=true`。进程离线时仍可展示有界历史，来源进程状态、数据目录可读性、新鲜度和逐会话状态分开；本机文件无权威逐会话状态时保留 `unknown`，不得伪造成 idle。Codex App 输出须校验 `session_meta` UUID；Claude 子 Agent 只能从已知 session/subagents 文件布局读取并校验父会话与 agentId。文本脱敏后仅留在本机 Provider/Host 内存，不写到日志或公开证据；Codex thread 导航只由用户点击受限 `codex://threads/<UUID>` Host 动作触发。

模型额度来源规则：TeamSense 本机 collector 只作实现参考；WinCraft 不调用 TeamSense API，也不需要 TeamSense `data:read` token。Codex rollout quota 只解析有界 `sessions/` 与 `archived_sessions/` JSONL 尾部中的 `event_msg.token_count.rate_limits` 字段，不读对话正文、`auth.json`、state SQLite，不启动或连接 Codex App；缺少有效事件时保持 `unknown`。Codex live quota 是独立默认关闭的实验性来源，只能由明确的 `--codex-quota` opt-in 使用；固定 HTTPS GET、有界响应、拒绝重定向，内存中只使用必要 `auth.json` 字段，不刷新/写回/上传，不显示或记录令牌及账户 ID，切号或身份不明时清除旧数据。DeepSeek/MiniMax 各自固定 HTTPS GET 也须独立显式 opt-in，key 只在对应 flag 启用后从本机环境读取；不得使用 TeamSense API、宽泛 dashboard、管理员、刷新或写入路由。自动测试只用合成 fixture 与模拟 HTTP，真实凭据、rollout 内容和供应商网络请求不得写入证据。宿主本身不读取 Codex 凭据。

默认允许：在解压工作目录中修改源码、安装正常开发依赖、构建、运行本项目测试与创建临时测试世界。先列计划并分步报告依据，不重复问用户已经决定的问题。

默认不允许：创建远程仓库、改外心安装目录或真实业务数据、用外心写 API 测试、将 token 写入证据、开放公网端口、悄悄改变许可、宣称未经实测的资源占用或原生能力。提交/推送需用户当轮明确授权；获得授权后也只操作已核实的既有仓库与 remote。

质量规则：每次变更写明原因；优先通过 core/server 测试再进入 Tauri；记录实际命令、退出码、环境和未验证项；保留 `NOT_RUN` 而不是填造绿色结果。浏览器演示与真实协议测试必须分别报告。引入的 lockfile 由本机实际依赖解析生成，不编造它们。

Tauri `Builder::setup` 是同步回调；后台异步循环要用 `tauri::async_runtime::spawn` 或显式 runtime handle 调度，不能在 setup 线程直接调用 `tokio::spawn`。

本地开发环境与统一验证入口见 [`docs/engineering/DEVELOPMENT_TOOLCHAIN.md`](docs/engineering/DEVELOPMENT_TOOLCHAIN.md)。功能变更先写一个可观察的 Given/When/Then 场景，再用对应层级的行为测试验证；静态检查、fixture、真实宿主和人工验收分开记录。

不要泄漏 `.runtime.json` 或其中的 bearer token。`evidence/local/` 是机器本地证据，可能含真实凭据、绝对路径、运行日志；保持忽略状态，不直接复制为公开证据，也不覆盖原始记录。分享摘要只使用合成或汇总数据并逐项检查。

仓库边界：WinCraft 核心与具有独立版本/发布周期的 Provider/应用分仓，子项目统一使用 `wincraft-XXX`；教程与合成 fixture 可留在核心仓库，不维护重复源码作为第二真相。世界存档只允许无业务数据的蓝图/模板，真实世界状态留在本机或其业务数据源。当前仓库保持私有；长期公开意向不等于本轮改变仓库可见性的授权。

任何仓库公开前，检查暂存、未跟踪与跟踪文件、全部可达 Git 历史和 tags、LFS、release 附件、截图及证据；扫描凭据并人工审查个人路径/标识、笔记/业务内容、遥测、runtime 描述文件、第三方许可与来源。就地扫描工作树，不要复制含凭据文件到临时目录；扫描输出只记录脱敏定位。若凭据曾进入历史，按已泄露处理并清理历史后再公开，不能只清理 HEAD。发布门槛通过后仍须遵从用户当轮对可见性变更的授权。

当前包本身只授权本地交接，不构成发布授权；用户另行授权的提交/推送不等于创建远程仓库或发布产品。

## 2026-10-26 平台演进交接包

执行入口与机器可读任务账本见 [`docs/strategy/2026-10-26/START_HERE.md`](docs/strategy/2026-10-26/START_HERE.md)。该目录里的新 schema 和 API 均为提案，不能称为协议 0.3 已实现；先核对当前源码、能力表和状态，再按依赖推进。所有新增可选组件/行为先在 host 能力表宣告，并让 Provider SDK 缺能力时失败关闭；不能只靠 JSON Schema 放行。`P-POPUP` 仅保留必要的运行契约摘要，不复制受限技能全文或公开其定位链接。规划包自检只证明规划资产一致，不证明 WinCraft 运行时或 Windows UI 已验收。

`.wcp` 有两种互斥的 manifest kind：`wincraft.pack.draft` 是 `0.4-preview.1` 配置包，只含蓝图和能力声明，不携带 Provider 可执行文件、runtime descriptor、凭据、业务状态或原机坐标，绝不下载/运行 adapter；`wincraft.provider-bundle` 是独立的本机代码包，拖入只校验/预览，安装只解包，必须先展示来源、entrypoint、摘要和任意代码警告，再由用户单独确认启动。Provider bundle 不自动安装依赖；只用无 shell 的受限 runtime adapter，连接描述文件只在用户确认启动后传给子进程。Provider 的 capability 是自我声明，不是 grant；配置包权限 grant 只由可信本机管理器在用户批准后写入，generation 变化后必须重新预览。配置包 apply 仅在本机用户确认后创建新世界；回退只清除与本次内存 ledger 一致且未被后续修改/加入的资源，不能覆盖或回滚用户既有世界。
