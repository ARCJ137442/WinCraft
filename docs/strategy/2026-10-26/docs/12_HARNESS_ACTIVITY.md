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

首屏使用一个全局悬浮世界呈现用户选定的 Harness 来源。默认摘要突出 Codex 并行会话数量和 Claude Code 各会话状态；用户可切换来源、实例或会话，进入选中范围后再展开任务/依据详情。切换视图不得另开每来源常驻窗口，也不得丢失来源身份、新鲜度、父子关系或撤销状态。完整提示词和会话日志不默认进入总览；观察本身不授予批准、写入或继续执行权限。长列表按需披露，窗口高度应适配当前视图而不过度撑高。

## 标准活动投影（提案）

统一 `device_id / provider_id / source_instance_id / source_type / session_id / parent_session_id / task_id`。PID、窗口标题、项目路径都不是跨设备稳定身份。`source_status` 保留来源原值，`normalized_status` 使用 `idle / running / waiting_input / waiting_approval / completed / failed / cancelled / unknown / stale`，同时保留 `mapping_version`。连接/新鲜度单独用 `freshness` 表达 `fresh / stale / disconnected / unknown`；不把断线自动写成业务终态。

必须附 source revision/sequence、observed_at、expires_at、权威级别与可用动作。发现后加入、心跳过期离线、重连生成新实例；“进程还在”不代表 Agent 忙，“没有日志”不等于已完成。父子会话允许多层，不把子任务重复计入母任务汇总。

### 仓库内 B08-01 提案原型

`protocol/activity.schema.json` (`draft-2026-10-29`) 将原始 `source_status`、映射后的 `normalized_status` 与 `freshness` 分开；它是原始 handoff `draft-2026-10-26` 的仓库实现提案，未替换已保留的 handoff schema。身份键只由 `device_id / provider_id / source_instance_id / session_id` 组成；显示名与模型名仅作标签。若 freshness 为 `stale` 或 `disconnected`，normalized status 必须为 `stale`；未知新鲜度对应 `unknown`，不能回落到 `idle`。

`examples/integrations/agent-board/` 目前只使用仓库内的 synthetic fixtures。聚合器要求每个来源批次带完整父子树，遇到重复身份、缺失父项或循环就失败关闭；父节点仍可呈现，但统计只计叶会话。B08-01 的 `control_capabilities` 必须为空，界面只用现有只读组件，不带批准、写文件或继续执行动作。仓库 schema 是 `draft-2026-10-29` 提案；原始 handoff `draft-2026-10-26` 保持不变，二者都不是 protocol 0.3 接口或真实 Harness 适配。

## Harness 适配证据表

| 来源 | 本轮一手资料支持的入口 | 首轮只做 | 不承诺 |
|---|---|---|---|
| Codex | App Server 双向请求与 thread/turn/item 通知 | 指定实例的任务/等待投影 | 自动发现用户所有既有 CLI 会话或直接接管审批 |
| Claude Code | Hooks、Notification、PermissionRequest 等扩展点 | 经用户配置的状态 hook | 一种事件在所有模式/版本行为相同 |
| OpenCode | 服务/事件流与插件 session/permission 事件 | 指定服务只读订阅 | 非授权服务可被自动读写 |
| DeepSeek Harness | 插件服务、session/agent/capability 事件与可撤销注册 | 只读插件 Adapter | 预览 API 稳定或完全兼容当前所有版本 |
| omp | 项目 README 的 SDK/RPC/ACP 入口 | 固定版本与模式的事件映射 | 所有模式都能回答同样的 UI/approval 请求 |

[X-CODEX][X-CLAUDE][X-OPENCODE][X-DSH][X-OMP]

每个 adapter 记录精确版本与运行模式；未知上游枚举映射 unknown 并保留原值。SDK/日志格式变化不应要求修改 WinCraft Core，只更新 provider adapter 与兼容 fixture。

## 决策与观察严格分开

面板可以显示“有三项等待你”，但批准必须回到原请求，并携带请求 ID、source epoch、操作摘要、当前有效性与用户授权。观察权限不推导批准权限；禁止一个“全部允许”按钮未经逐项契约审查即批量放行。

弹出的审批只是外层呈现；原 Harness 的拒绝规则、sandbox、policy 仍生效。事件回复 timeout 后状态为 unknown，需要读取权威状态，不自动重发允许。普通 idle 通知不能当 approval。

## 第一条真实验收

选择两个已有可用 Harness：一个产生工作状态、一个产生取消或等待输入。先做各自只读；然后单独接入一个真实结构化问题。随后销毁一个 session、重启 adapter、重用相同显示名，保证旧卡片不获得新实例写权。五种 Harness 都在路线内，不要求第一批同时完成。
