---
{
  "doc_id": "sources__README",
  "title": "来源与复核方法",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "evidence-index",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE",
    "P-POPUP",
    "P-SYSTORCH-LOCAL"
  ]
}
---

# 来源与复核方法

`registry.json` 是来源单一索引。正文 `[来源ID]` 对应其中的 URL（受限来源会省略定位）、读取日期、版本与结论边界。包作者报告的来源日期是 2026-10-26；这不是本地重新访问所有外部来源的证明。实施涉及接口时须重新读取并固定版本。

本包不收录私有技能全文、真实用户数据或 runtime descriptor。公开仓库副本已移除 `P-POPUP` 的受限仓库 URL，只保留当前本机可读到的必要契约摘要和来源标识；不在文档、示例或证据中记录用户机器上的技能安装路径。SysTorch 本地 M1 候选的身份与当前工作树 API 已只读核对，但其相关实现仍未提交、未发行；它只能作为候选契约依据，不能冒称稳定 Release API 或 live integration。TeamSense 精确来源/API 仍未定位。

来源类型：用户决定→规范约束；源码观察→静态事实；仓库报告→已有作者验收；官方文档→技术参考；本包方案→待实现假设。几者不可混成一个 PASS。

本轮未把Minecraft历史、商标、市场规模或性能优越性当作架构成立的证据。Minecraft是模型隐喻，WinCraft的成功依靠可验证的创作路径。
