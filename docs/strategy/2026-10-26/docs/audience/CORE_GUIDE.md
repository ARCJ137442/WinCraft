---
{
  "doc_id": "docs__audience__CORE_GUIDE",
  "title": "内核层：不变量比组件数量重要",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "core-design-guide",
  "audience": "kernel-maintainer",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 内核层：不变量比组件数量重要

保持身份、权限、生命周期、结果语义与版本的唯一裁决。整窗写lease与快照读者不是Rust共享/可变引用；子树切分以后必须连数据命名空间、动作路由、结构事务和服务端读取过滤一起设计。

窗口意图接受与OS执行结果分开；业务成功与Host动作回执分开；可合并状态与不可静默丢失交互分开。每个注册效果应有scope、撤销、幂等清理和配额，不能让断线残留资源。

0.3的严格版本与deny_unknown_fields需要明确迁移，不可单方面往旧消息加字段并假定接受。安全根留Host；公开扩展机制不是公开operator。原生能力可复用，但跨平台语义需各自证据。

旧测试、真实Provider和用户救援是每批底线。运行时数据可重建不意味着没有状态；配置分享不意味着封存权限、提供者或业务历史。
