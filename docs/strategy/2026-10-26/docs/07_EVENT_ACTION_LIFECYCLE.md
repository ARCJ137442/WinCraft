---
{
  "doc_id": "docs__07_EVENT_ACTION_LIFECYCLE",
  "title": "事件、反应与可撤销资源",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "proposal",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 事件、反应与可撤销资源

## 三种通道不能混为一谈

**状态流**告诉接收方现在是什么，可合并为最新快照。**发生记录**表达隐藏、恢复、请求取消等离散事实，不可被默默合并掉。**命令与决策**具有关联 ID、期限和结果，传递成功不等于业务执行。

当前已有 snapshot 推送，不需要退回轮询后再“新增实时”。拟议类型订阅建立在当前 sequence/window_revision 上，事件带 `event_id`、世界/作用域、源实例、source_seq、因果 ID、发生与观测时间、内容最小化字段。不能新建一份与窗口投影互相竞争的真相。

2026-10-27 已实现 B04-01 的有限子集：协议 0.3 提供连接级订阅/取消，支持几何与逻辑显隐两种 `delivery=state` 事件；事件携带 event/subscription/world ID、source、cause_id、sequence、window_revision 与最小 payload。状态通过 per-world latest-value watch 合并，按钮交互和删除仍走独立有界 occurrence 队列。未实现时间戳、事件持久化、焦点/最小化事件或自动事件响应；不要把这批已实现能力扩大宣称为完整事件总线。

## 订阅与撤销

注册属于 session/scope；只订阅授权资源和事件种类；注销、断线、scope 撤销、operator hold 后清理。高级事件注册与高级动作授权相互独立：能看最小化不等于能聚焦任意应用。

参考 DSH/Cordis 的 registration-as-effect：订阅、热键、资源句柄都可注册并成组销毁；只借鉴生命周期语义，不把任意插件代码载入 Core。[X-DSH]

## 合并、背压和循环

几何等高频状态采用宿主本地 coalesce，并报告最新 sequence。控制事件独立有界队列；满时显式 overflow/resync_required，不丢掉批准/取消后装作成功。重建快照能够补状态，不能重演历史批准。需要持久决策记录时由源业务保存。

反应链带 causal_id、origin、hop budget。宿主自身兑现引发的回声不可无限递归；同一规则有冷却、并发上限与失败隔离。状态合并验收要求“最终状态正确且缺口可见”，不要求每一帧移动事件无损，这修正了旧路线图“合并又绝不丢任何移动事件”的含混要求。

## 可声明的本地动作

锚定、缓动、跟随等连续行为由宿主执行，远端只发目标意图和边界；不发每帧坐标。第一期仍让 Provider 处理业务条件，内核只标准化事件与受限动作。以后确有重复逻辑才加入有限规则，不扩成任意脚本语言。

## 人类决策的时限

人类问题可等待较长时间，但普通 `interaction` 的 10 秒 ack 不是提问超时。Provider 及时确认“已收到这一局部 UI 动作”，问题整体 `request_id` 仍按外层 deadline 等待。提交时才完成问题；关闭/取消/来源撤销/过期具有不同结果。多个终端结果竞争时由一个权威协调者决定一次；对外副作用仍依赖源业务幂等机制。
