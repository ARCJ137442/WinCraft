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

首屏使用一个全局悬浮世界呈现用户选定的 Harness 来源。Claude Code、Codex CLI 与 Codex App 保留独立 source identity 和采集状态。Codex CLI 继续用 `thread/list` 并固定 `useStateDbOnly=true`；Codex App 只读本机 `state_*.sqlite` 中 `originator=Codex Desktop` 的有限行，并在 `session_meta` UUID 匹配后读最近 rollout 的有界 Agent 输出；Claude Code 从配置项目目录里的会话 JSONL 与已知 `session/<UUID>/subagents/agent-*.jsonl` 读取历史。Codex App 与 Claude Code 的在线/离线只由 OS 进程元数据决定；采集不会启动它们，也不调用 App MCP、Claude CLI 状态命令或连接器。进程离线时仍保留可读历史，逐会话状态没有权威字段时显示 `unknown`，不伪造成 idle。来源进程状态、磁盘数据可读性和最近成功读取年龄分别呈现。

用户可切换来源、实例或会话，进入选中范围后再展开任务/依据详情。切换视图不得另开每来源常驻窗口，也不得丢失来源身份、新鲜度、父子关系或撤销状态。完整提示词和会话日志不默认进入总览；观察本身不授予批准、写入或继续执行权限。长列表按需披露，窗口高度应适配当前视图而不过度撑高。Codex App 的 `codex://threads/<UUID>` 导航只能经宿主声明能力和用户点击触发。

## 标准活动投影（提案）

统一 `device_id / provider_id / source_instance_id / source_type / session_id / parent_session_id / task_id`。PID、窗口标题、项目路径都不是跨设备稳定身份。`source_status` 保留来源原值，`normalized_status` 使用 `idle / running / waiting_input / waiting_approval / completed / failed / cancelled / unknown / stale`，同时保留 `mapping_version`。连接/新鲜度单独用 `freshness` 表达 `fresh / stale / disconnected / unknown`；不把断线自动写成业务终态。

必须附 source revision/sequence、observed_at、expires_at、权威级别与可用动作。发现后加入、心跳过期离线、重连生成新实例；“进程还在”不代表 Agent 忙，“没有日志”不等于已完成。父子会话允许多层，不把子任务重复计入母任务汇总。

### 仓库内 B08-01 提案原型

`protocol/activity.schema.json` (`draft-2026-10-29`) 将原始 `source_status`、映射后的 `normalized_status` 与 `freshness` 分开；它是原始 handoff `draft-2026-10-26` 的仓库实现提案，未替换已保留的 handoff schema。身份键只由 `device_id / provider_id / source_instance_id / session_id` 组成；显示名与模型名仅作标签。若 freshness 为 `stale` 或 `disconnected`，normalized status 必须为 `stale`；未知新鲜度对应 `unknown`，不能回落到 `idle`。

当前 Global Overview 为三个来源统一呈现会话名称、状态、项目标签与来源文本预览。项目只显示 `cwd` 的末级目录名，不输出完整路径。Codex CLI 的 `thread/list.preview` 发言方未标注，卡片标为“会话预览（发言方未标注）”。Codex App 标题与项目来自 Desktop-originator 状态行；最近 Agent 输出只来自 `session_meta.payload.id` 与本机线程 UUID 精确匹配后的有界 rollout 尾部。Claude Code 会话名优先取本地 `custom-title`/`ai-title`，输出只取匹配会话日志尾部的 assistant text；`thinking`、user prompt、tool output 不显示。主会话与已知子 Agent 日志都使用有界文件数/输出数，越界或身份不匹配显示 partial/unknown。短文本经过凭据/路径脱敏并作为纯文本渲染；不读取完整会话、执行批准或继续会话动作。

`activity_board.py` 的基础聚合和 B08-01 回归仍使用仓库 synthetic fixtures。`live_sources.py` 对 Codex Desktop 执行 query-only SQLite 与身份核验后的 bounded rollout 读取；对 Claude Code 只扫配置项目目录下的 JSONL 主会话与固定子 Agent 布局。Windows 用 Toolhelp32 读取进程名/父进程，并只为 Codex/Claude 候选查询映像路径；不取 command line、不启动 Harness。来源 health、data health 与读取新鲜度不互相替代。来源失败只使该来源的历史标陈旧/不可用。当前实现不再需要 Codex App connector relay；`codex://threads/<UUID>` 只在用户点击标题后由 Host 执行受限导航。聚合器要求每个来源批次带完整父子树，遇到重复身份、缺失父项或循环就失败关闭；父节点仍可呈现，但统计只计叶会话。B08-01 的 `control_capabilities` 必须为空，界面只用现有只读组件，不带批准、写文件或继续执行动作。仓库 schema 是 `draft-2026-10-29` 提案；原始 handoff `draft-2026-10-26` 保持不变，二者都不是 protocol 0.3 接口或真实 Harness 适配。

Codex App/Claude Code 的本机读取时刻用于来源 freshness；磁盘文件的活动时刻只作 bounded session evidence，不冒充在线状态。进程存在也不能让所有会话显示 running；无权威逐会话状态时保持 unknown。读取失败保留最后成功年龄，数据目录仍可读时即使进程离线也继续显示历史。

## Harness 适配证据表

| 来源 | 本轮一手资料支持的入口 | 首轮只做 | 不承诺 |
|---|---|---|---|
| Codex CLI · 本机状态库 | Codex App Server `thread/list` | `useStateDbOnly=true` 的名称、状态、cwd 末级项目名与发言方未标注的短 preview | 将 preview 冒充 Agent 输出、读取 rollout JSONL 或完整 turn 内容 |
| Codex App | 只读最新 `state_*.sqlite` 的 Desktop-originator 行；校验 rollout `session_meta` 与 UUID 后读取有界尾部；进程状态匹配已知 Codex Desktop 映像/父进程 | 标题、项目、最近 Agent 输出、进程 online/offline、数据可读性与读取年龄；链接只带 UUID 并由 Host 构造 `codex://threads/<UUID>` | App MCP/API、启动 App Server、从进程存在推断每个会话运行、读取完整会话或工具输出 |
| Claude Code | 从 `~/.claude/projects` 或 `CLAUDE_CONFIG_DIR` 的项目 JSONL 主会话与固定子 Agent 文件布局读取；进程匹配本机安装映像 | 会话标题/项目/最近 assistant 文本；进程 online/offline 与读取新鲜度分开展示；离线仍可查看历史 | 调用 `claude agents --json`、扫描任意目录、展示 prompt/thinking/tool output、把缺失状态伪造成 idle |
| OpenCode | 服务/事件流与插件 session/permission 事件 | 指定服务只读订阅 | 非授权服务可被自动读写 |
| DeepSeek Harness | 插件服务、session/agent/capability 事件与可撤销注册 | 只读插件 Adapter | 预览 API 稳定或完全兼容当前所有版本 |
| omp | 项目 README 的 SDK/RPC/ACP 入口 | 固定版本与模式的事件映射 | 所有模式都能回答同样的 UI/approval 请求 |

[X-CODEX][X-CLAUDE][X-OPENCODE][X-DSH][X-OMP]

## 本机 Harness 版本与适配状态（2026-10-30）

以下是本机只读 `--version` 检查和已记录的来源 smoke。版本检查只证明命令可报告版本，不证明 Harness 会话可枚举或 Adapter 已接入。五类按 Codex、Claude Code、OpenCode、DeepSeek Harness、omp 组织；Codex CLI 与 Codex App 拆成独立来源行。

| Harness / source ID | 本机版本检查 | 已有适配证据 | 未完成边界 |
|---|---|---|---|
| Codex CLI / `codex` | `codex-cli 0.138.0-alpha.7` | `thread/list` 固定 `useStateDbOnly=true`；本机 read-only smoke 返回来源状态与可列会话数 | 空列表不等于无任务；不把 CLI 状态套到 Codex App。|
| Codex App / `codex-app` | 本机进程观察 | 只读 Desktop-originator state DB 与 UUID-verified rollout；进程在线、磁盘数据 partial 的 count-only smoke 通过 | 当前 release 窗口四字段呈现与真实 UUID-only 导航目标加载仍 NOT_RUN；不需要持续 connector relay。|
| Claude Code / `claude-code` | `2.1.302` | 本地项目 JSONL 主会话/子 Agent reader smoke 返回 `local_state`；进程 offline 时仍保留历史，不运行 `agents --json` | 只有日志可证的字段会展示；逐会话状态无权威证据时为 `unknown`；release UI 仍 NOT_RUN。|
| OpenCode / source ID 未分配 | `1.1.14` | 本地版本命令可用；设计入口是指定服务事件流/插件事件 | 本仓库没有 OpenCode adapter 实测；session、permission 事件和授权边界均 NOT_RUN。|
| DeepSeek Harness (`dsh`) / source ID 未分配 | `dsh --version` 失败，版本未知 | 本地命令存在；设计入口是插件服务与可撤销注册 | 当前安装无法报告版本；插件事件与只读 adapter 均 NOT_RUN。|
| omp / source ID 未分配 | `omp/15.5.7` | 本地版本命令可用；设计入口来自项目 README 的 SDK/RPC/ACP | 本仓库没有 omp adapter 实测；固定模式的事件映射与权限边界均 NOT_RUN。|

本轮真实来源读取只包含明确选择的 Codex CLI 与 Claude Code；OpenCode、DSH、omp 的会话和服务均未探测。此表证明 B08-03-A1 的入口和未知边界已明确，不计作五种 Harness 均已实测。

每个 adapter 记录精确版本与运行模式；未知上游枚举映射 unknown 并保留原值。SDK/日志格式变化不应要求修改 WinCraft Core，只更新 provider adapter 与兼容 fixture。

## 决策与观察严格分开

面板可以显示“有三项等待你”，但批准必须回到原请求，并携带请求 ID、source epoch、操作摘要、当前有效性与用户授权。观察权限不推导批准权限；禁止一个“全部允许”按钮未经逐项契约审查即批量放行。

弹出的审批只是外层呈现；原 Harness 的拒绝规则、sandbox、policy 仍生效。事件回复 timeout 后状态为 unknown，需要读取权威状态，不自动重发允许。普通 idle 通知不能当 approval。

## 第一条真实验收

分别验证 Claude Code 本地会话文件、Codex CLI 本机状态库与 Codex App 本机状态文件。来源进程状态、数据目录可读性、session 状态与更新时间彼此独立；单源读取失败只影响自身投影。Codex App 标题点击只通过 Host 构造的 UUID-only 深链接；该点击和 release 可见 UI 仍需验收。Computer Use 激活失败时不重放旧句柄或坐标；在可用的 UIA 路径恢复后继续。

**2026-10-30 决策更新：** 用户明确不需要与 Codex App 实时通信，也不需要为采集启动 Codex App 或 Claude Code。先前“持续 connector relay / Codex App STALLED”是阶段性记录，现由本节的进程 + 本机文件方案取代；B08-02 状态为 `IN_PROGRESS`，原生 UI/UUID 深链接仍是独立未验项。
