---
{
  "doc_id": "evidence__README",
  "title": "交接包自身验证边界",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "validation-scope",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 交接包自身验证边界

`package-validation.json`与`unit-tests.log`由本次真实执行产生，范围仅为本文档、任务追踪、Schema样例、纯数据规划器和元数据一致性。它们不改变plan/acceptance.json里新增产品用例的NOT_RUN。

本次未克隆并编译当前WinCraft运行时、未操作Windows、未连真实Harness、网页账号或Android通知，也未修改远端仓库。GitHub读取支持静态基线；仓库中的已有测试结果仍称REPO_REPORTED。

本包文档last_verified_at表示相关资料/文档状态检查日期；不表示对应功能实机验证。源码、协议或参考版本变化应触发复核；元数据不能替代测试日志。

安全审查只检查明显的运行文件名、包内链接、路径与示例边界，不是渗透测试或完整秘密扫描认证。负fixture故意包含虚构token字段，用于证明拒绝；不要将其当真实凭据。
