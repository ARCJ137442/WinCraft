---
{
  "doc_id": "docs__00_BASELINE_AND_EVIDENCE",
  "title": "基线、证据与未知边界",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "verified-scope",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "W-BASELINE",
    "W-VALIDATION",
    "W-MODEL",
    "W-TRANSPORT",
    "P-POPUP",
    "P-SYSTORCH-LOCAL"
  ]
}
---

# 基线、证据与未知边界

## 固定快照

目标仓库：`ARCJ137442/WinCraft`；观察分支：`dev`；固定提交：`6929056700b1ba6702288534579debc8a502c139`；取证日期：2026-10-26。[W-BASELINE]

已读 `AGENTS.md`、提供者 Skill、验证摘要、仓库树、`model.rs` 与 `transport.rs` 关键片段。当前源码 `PROTOCOL = "0.3"`、`LEASE_MS = 15_000`、`ACTION_TIMEOUT_MS = 10_000`。网络仅回环监听，带 Origin 的请求被拒绝。[W-MODEL][W-TRANSPORT]

## 证据等级

| 标签 | 意义 | 可作什么结论 |
|---|---|---|
| USER_DECIDED | 用户明确决定 | 作为设计约束，不意味着运行通过 |
| SOURCE_OBSERVED | 本轮读取源码/官方文档 | 支持该快照范围内的静态事实 |
| REPO_REPORTED | 仓库已有验收摘要 | 可注明“仓库记录”，不得当本轮独立复测 |
| PROPOSED | 本包给出的方案 | 可实施、可被实验推翻，不是现有 API |
| VERIFIED_LOCAL | 本包工具在当前环境执行 | 仅覆盖包内检查与纯数据模型 |
| NOT_RUN / BLOCKED | 未执行或受阻 | 列明缺失环境/来源，不计 PASS |

交接包固定基线中的仓库摘要曾记录 Rust 测试、19 项真实 0.3 协议探针、TrafficMonitor 与 Obsidian Workspace 原生投影；这只是基线快照，不是当前计数。后续本机结果与仍待验收项以 `plan/status.json`、根目录 `docs/engineering/VALIDATION.md` 和被忽略的本机证据为准。不要把旧“制作环境没有 Cargo”的历史表格误读成当前 dev 没跑过 Rust，也不要把任一摘要扩大成全部已验收。[W-VALIDATION]

## 接入来源边界

`popup-question` 是用户本轮称呼；本轮实际定位的团队技能为 `popup-ask`。按可读取的技能契约设计兼容层，不擅自改名或执行它来重新问用户。[P-POPUP]

SysTorch：本机已找到 SysTorch（原 Jev Switch）工作树并只读核对其 M1 决策 API。相关路由、存储模块与契约仍未提交、未发行，不能视为稳定 Release API；本轮未启动服务、读取凭据或访问业务任务。B03-03 仍等待 B03-02 与明确运行时信息。TeamSense：用户意图与历史讨论明确，本轮没有核验其现行接口；不得猜端点、账户或额度口径。

TouchAI：读取了 `TouchAI-org/TouchAI` README，可作为候选项目资料；需要本地与协作者确认目标 commit 和现有配置。README 的快捷入口、上下文和工具描述不能证明“全部可迁入 WinCraft”。[P-TOUCH]

AndroMorph：以前文项目记录与用户本轮目标为需求依据；真实外部通知、传输网络及真机权限链路必须重新验收。DSH、omp、Codex、Claude Code、OpenCode 的文档只能支持适配入口选择，不能证明能发现所有已运行会话。[X-DSH][X-OMP][X-CODEX][X-CLAUDE][X-OPENCODE]

## 本轮没有做的事

没有修改/推送远端；没有运行 Windows 或移动设备；没有读取 API Key、运行时 descriptor 内容、通知、浏览器 Cookie、私人会话或真实业务。尝试通过容器下载公开源码归档时 DNS 不可用，已停止；未把原 0.1.0 交接 ZIP 当成本次最新检出。后续实现依赖本地真实仓库。

全部来源定义见 [注册表](../sources/registry.json)；提交和文件哈希见 [基线清单](../sources/baseline.json)。
