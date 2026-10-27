---
{
  "doc_id": "governance__REVIEW_CHECKLIST",
  "title": "每批合入审查",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "normative-plan",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 每批合入审查

本表只承担评审入口；具体用例在任务和验收矩阵。

- 用户最新约束是否满足，旧建议冲突是否登记；该改动是否真需要进入公共内核。
- 原有 0.3 Provider 能否继续工作；新能力是否查询/授权/取消/回执/恢复齐全。
- 资源所有权、数据读取范围、epoch、版本冲突和父子撤销是否测试。
- UI 是否保留草稿、IME、键盘、无障碍、来源真实性、中英与主题回退。
- 是否仅使用合成数据或显式授权真实来源，日志/包/截图是否含秘密。
- 文档基线、更新时间、状态、来源与翻译 hash 是否同步；NOT_RUN 是否保留。
- 回滚是否可执行；发布/推送是否有独立授权；最终结论是否只覆盖证据范围。
