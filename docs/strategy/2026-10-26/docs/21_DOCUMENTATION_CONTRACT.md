---
{
  "doc_id": "docs__21_DOCUMENTATION_CONTRACT",
  "title": "文档时效、分层与 Luna 必须遵守的规则",
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

# 文档时效、分层与 Luna 必须遵守的规则

## 每份规范文档的元信息

至少 `doc_id / updated_at / last_verified_at / baseline_commit / protocol_baseline / status / owner_role / audience / source_ids / review_trigger`。本包用 JSON front matter（也是合法 YAML）方便无额外解析器检查。

`updated_at` 是实际编辑日期，`last_verified_at` 是该文档对来源的核查日期，**不是运行验证日期**。实现状态分别标 USER_DECIDED、PROPOSED、SOURCE_OBSERVED、REPO_REPORTED、VERIFIED_LOCAL、NOT_RUN、BLOCKED。禁止只改日期而不核查内容。

## 单一真源

用户需求在 `plan/requirements.json`；任务在 `plan/tasks.json`；架构决定在 `plan/decisions.json`；验收状态在 `plan/status.json`；外部依据在 `sources/registry.json`。Markdown 任务索引和追踪表为生成视图，不手工编辑制造第二份计划。

正文按主题独占职责：用户指南讲操作、专业文档讲契约、代码注释讲局部实现。跨主题用链接，不把同一权限清单复制到五个文件。旧文件应标 superseded 并链接新权威文档，不能静默删除历史语义。

## 改代码时同步范围

协议变更：Rust 类型、Schema、SDK、正反 fixture、错误表、能力/版本文档、Agent skill。

组件变更：renderer、style/token、可访问性、i18n、示例与截图状态。

原生能力：平台矩阵、授权、原生回执、失败恢复、release 证据。

适配器变更：来源版本、端点/事件证据、未知值与降级、隐私、兼容 fixture。

## 翻译纪律

机器标识保持英文稳定，解释至少中英两层入口。译文带源文路径及 hash/revision；源文变化即标 stale，CI 阻止将 stale 写成 current。未知内容不得为了补齐翻译而增加承诺。

## 时间与时区

日期用 ISO 8601；事件用含时区时间戳；来源发生时间和接收时间分开。不能把不同机器时间戳直接当严格顺序；顺序由对应源序号/实例决定。文档不使用无锚定的“最近/已经/目前全支持”。

## 规则落盘

把 [AGENTS 增补](../governance/AGENTS_APPENDIX.md) 审阅合并进现有 `AGENTS.md`，保持已有安全规则。把本包 lint 规则纳入项目 CI，但先扫描只新增/修改规范文档，给历史材料迁移批次；不要为全仓格式统一而改写所有历史文档。
