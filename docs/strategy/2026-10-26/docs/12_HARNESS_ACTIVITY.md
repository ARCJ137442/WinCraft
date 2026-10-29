---
{
  "doc_id": "docs__12_HARNESS_ACTIVITY",
  "title": "多 Harness 状态聚合与人类待办",
  "updated_at": "2026-10-29",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "proposal",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "X-CODEX",
    "X-CLAUDE",
    "X-OPENCODE",
    "X-DSH",
    "X-OMP"
  ]
}
---

# 多 Harness 状态聚合与人类待办

## 两种架构阶段

近期可用一个聚合 Provider 接收多个来源的只读活动，再独占写一个世界。这不等于已支持多个 Provider 同写，也不是必须等组件级借用才做原型。

B07 完成后，每个 Harness adapter 获得自己的子树/数据 scope；布局 authority 负责面板布局，不能替各 Harness 改业务。读者聚合可以重新投影，但不得把数据的来源/新鲜度抹掉。

## 全局悬浮总览与渐进披露

首屏使用一个全局悬浮世界呈现用户选定的 Harness 来源。Claude Code 后台 Agent、Codex CLI 本机状态库、Codex App 两种采集通道必须保留独立 source identity 和采集状态：Claude `agents --json` 返回后台 Agent 记录，不等于列出全部交互式会话；Codex CLI `thread/list` 固定限制为本机 state DB；Codex App 可由有权 Agent connector 提供快照，也可只读读取本机 `state_*.sqlite` 中 `originator=Codex Desktop` 的有限会话元数据。后者不能证明运行状态；打开 Codex App 本身也不代表 connector 快照已到达 Provider。来源“可查询”与其中会话“运行/阻塞/空闲”分开展示，并显示每个来源最近成功读取年龄。Codex App 会话行展示标题、状态、项目和最近 Agent 输出，详情逐步披露同一会话的更多信息。

用户可切换来源、实例或会话，进入选中范围后再展开任务/依据详情。切换视图不得另开每来源常驻窗口，也不得丢失来源身份、新鲜度、父子关系或撤销状态。完整提示词和会话日志不默认进入总览；观察本身不授予批准、写入或继续执行权限。长列表按需披露，窗口高度应适配当前视图而不过度撑高。Codex App 的 `codex://threads/<UUID>` 导航只能经宿主声明能力和用户点击触发。

## 标准活动投影（提案）

统一 `device_id / provider_id / source_instance_id / source_type / session_id / parent_session_id / task_id`。PID、窗口标题、项目路径都不是跨设备稳定身份。`source_status` 保留来源原值，`normalized_status` 使用 `idle / running / waiting_input / waiting_approval / completed / failed / cancelled / unknown / stale`，同时保留 `mapping_version`。连接/新鲜度单独用 `freshness` 表达 `fresh / stale / disconnected / unknown`；不把断线自动写成业务终态。

必须附 source revision/sequence、observed_at、expires_at、权威级别与可用动作。发现后加入、心跳过期离线、重连生成新实例；“进程还在”不代表 Agent 忙，“没有日志”不等于已完成。父子会话允许多层，不把子任务重复计入母任务汇总。

### 仓库内 B08-01 提案原型

`protocol/activity.schema.json` (`draft-2026-10-29`) 将原始 `source_status`、映射后的 `normalized_status` 与 `freshness` 分开；它是原始 handoff `draft-2026-10-26` 的仓库实现提案，未替换已保留的 handoff schema。身份键只由 `device_id / provider_id / source_instance_id / session_id` 组成；显示名与模型名仅作标签。若 freshness 为 `stale` 或 `disconnected`，normalized status 必须为 `stale`；未知新鲜度对应 `unknown`，不能回落到 `idle`。

当前 Global Overview 为三个来源统一呈现会话名称、状态、项目标签与来源文本预览。项目只显示 `cwd` 的末级目录名，不输出完整路径。Codex CLI 的 `thread/list.preview` 发言方未标注，卡片标为“会话预览（发言方未标注）”；Claude Code `agents --json` 不提供最近输出，卡片明确显示来源缺少该字段。Codex App 的 connector `agent_message`，或通过 `session_meta.payload.id` 与本地线程 UUID 精确匹配后读取的有界 rollout `agent_message`/`task_complete.last_agent_message`，才可标为“最近 Agent 输出”。本机回退最多读取最近四条 rollout 的尾部 1 MiB；不匹配时不显示输出。短文本先经过凭据/路径脱敏并作为纯文本渲染；这不授权读取完整 rollout、全量日志或批准/执行会话操作。

`activity_board.py` 的基础聚合和 B08-01 回归仍使用仓库 synthetic fixtures。`live_sources.py`、`live_provider.py` 实现 Claude/Codex CLI 只读适配、Codex App connector 快照桥和 Desktop 本机状态回退；本机回退仅读 query-only SQLite、筛选精确 Desktop originator，并在 rollout 身份匹配后读取有限尾部，不扫描完整会话日志。当前 release 对持续 Codex App connector relay 的验收仍为 `BLOCKED`，不能把合成 fixture 或一次性 provider 协议回执视为实时 UI 接入。聚合器要求每个来源批次带完整父子树，遇到重复身份、缺失父项或循环就失败关闭；父节点仍可呈现，但统计只计叶会话。B08-01 的 `control_capabilities` 必须为空，界面只用现有只读组件，不带批准、写文件或继续执行动作。仓库 schema 是 `draft-2026-10-29` 提案；原始 handoff `draft-2026-10-26` 保持不变，二者都不是 protocol 0.3 接口或真实 Harness 适配。

Codex App connector 快照若带 `captured_at`，Provider 用它计算来源年龄及会话 TTL；缺少时间的旧格式回退为本机接收时刻。无时区、格式错误或未来时间戳只使 Codex App 这一路失败关闭；到达 TTL 边界即标 stale。不能把消息到达 Provider 的时间冒充来源刚刚读取。

## Harness 适配证据表

| 来源 | 本轮一手资料支持的入口 | 首轮只做 | 不承诺 |
|---|---|---|---|
| Codex CLI · 本机状态库 | Codex App Server `thread/list` | `useStateDbOnly=true` 的名称、状态、cwd 末级项目名与发言方未标注的短 preview | 将 preview 冒充 Agent 输出、读取 rollout JSONL 或完整 turn 内容 |
| Codex App connector | 经用户授权的 Agent 从 Codex App MCP connector 提供 `list_threads` / `list_projects`；active 项的 `read_thread` 限量取最近 Agent 消息 | 权威状态/快照，显示标题、状态、项目与限长输出；链接只带 UUID 并由 Host 构造 `codex://threads/<UUID>` | App 打开即自动连入、任意 URL/命令、批准或继续执行 |
| Codex App · 本机回退 | 只读 `state_*.sqlite` 中精确标记为 `Codex Desktop` 的有限行；可选读取 UUID 匹配 rollout 的有界尾部 | 补充标题/项目；无权威状态时为 `unknown`；无匹配 Agent 输出时显示不可用 | 推断运行状态、读取完整会话、把用户消息或工具输出当 Agent 输出 |
| Claude Code | 本机 `agents --json` 后台 Agent 状态接口；Hooks/Notification 是其他适配模式 | 显示后台 Agent 名称、状态、cwd 末级项目名与 CLI 可查询状态；无输出字段时明确显示缺失 | 把后台 Agent 记录当作全部交互会话，推断其最近输出，或用 CLI 查询成功推断 GUI 会话在线 |
| OpenCode | 服务/事件流与插件 session/permission 事件 | 指定服务只读订阅 | 非授权服务可被自动读写 |
| DeepSeek Harness | 插件服务、session/agent/capability 事件与可撤销注册 | 只读插件 Adapter | 预览 API 稳定或完全兼容当前所有版本 |
| omp | 项目 README 的 SDK/RPC/ACP 入口 | 固定版本与模式的事件映射 | 所有模式都能回答同样的 UI/approval 请求 |

[X-CODEX][X-CLAUDE][X-OPENCODE][X-DSH][X-OMP]

## 本机 Harness 版本与适配状态（2026-10-30）

以下是本机只读 `--version` 检查和已记录的来源 smoke。版本检查只证明命令可报告版本，不证明 Harness 会话可枚举或 Adapter 已接入。五类按 Codex、Claude Code、OpenCode、DeepSeek Harness、omp 组织；Codex CLI 与 Codex App 拆成独立来源行。

| Harness / source ID | 本机版本检查 | 已有适配证据 | 未完成边界 |
|---|---|---|---|
| Codex CLI / `codex` | `codex-cli 0.138.0-alpha.7` | `thread/list` 只读 adapter 与当前 release smoke：source `online`，本次 0 条可列会话 | 此次没有可呈现的会话行；不能把空列表推成无任务或把 CLI 状态套到 Codex App。|
| Codex App / `codex-app` | NOT_RUN | 一次授权 connector 快照曾到达 Provider；本轮明确 `not_requested` | 持续 relay、真实 release 列表、Agent 输出和 UUID 深链接仍 STALLED / NOT_RUN。|
| Claude Code / `claude-code` | `2.1.302` | `agents --json` 只读 adapter 与当前 release smoke：source `online`，2 条后台 Agent 状态为 `blocked` | CLI 返回的后台 Agent 集合不等于全部交互会话；此证据没有验证最近 Agent 输出。|
| OpenCode / source ID 未分配 | `1.1.14` | 本地版本命令可用；设计入口是指定服务事件流/插件事件 | 本仓库没有 OpenCode adapter 实测；session、permission 事件和授权边界均 NOT_RUN。|
| DeepSeek Harness (`dsh`) / source ID 未分配 | `dsh --version` 失败，版本未知 | 本地命令存在；设计入口是插件服务与可撤销注册 | 当前安装无法报告版本；插件事件与只读 adapter 均 NOT_RUN。|
| omp / source ID 未分配 | `omp/15.5.7` | 本地版本命令可用；设计入口来自项目 README 的 SDK/RPC/ACP | 本仓库没有 omp adapter 实测；固定模式的事件映射与权限边界均 NOT_RUN。|

本轮真实来源读取只包含明确选择的 Codex CLI 与 Claude Code；OpenCode、DSH、omp 的会话和服务均未探测。此表证明 B08-03-A1 的入口和未知边界已明确，不计作五种 Harness 均已实测。

每个 adapter 记录精确版本与运行模式；未知上游枚举映射 unknown 并保留原值。SDK/日志格式变化不应要求修改 WinCraft Core，只更新 provider adapter 与兼容 fixture。

## 决策与观察严格分开

面板可以显示“有三项等待你”，但批准必须回到原请求，并携带请求 ID、source epoch、操作摘要、当前有效性与用户授权。观察权限不推导批准权限；禁止一个“全部允许”按钮未经逐项契约审查即批量放行。

弹出的审批只是外层呈现；原 Harness 的拒绝规则、sandbox、policy 仍生效。事件回复 timeout 后状态为 unknown，需要读取权威状态，不自动重发允许。普通 idle 通知不能当 approval。

## 第一条真实验收

分别验证 Claude Code 后台 Agent、Codex CLI 本机状态库、Codex App connector 和 Codex Desktop 本机回退。先确认来源健康、session 状态与更新时间彼此独立；单源断开只影响自身投影。Codex App 后续还须验证持续授权快照、四字段行与 UUID-only 深链接；本机回退须保持状态未知并在身份不匹配时拒绝输出。当前 Codex App 子目标标记为 `STALLED`：一次性快照曾到达 Provider，但持续 relay、release UI 和原生深链接尚未验收；Computer Use 激活失败后不重复 UI 操作。其他 Harness 仍在路线内，不要求第一批同时完成。
