---
{
  "doc_id": "INDEX",
  "title": "全包导航与唯一事实来源",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "navigation",
  "audience": "human, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 全包导航与唯一事实来源

本索引只导航，不重新定义规范。用户最新要求见需求追踪；下一步实现见任务表。

## 入口

| 文档 | 用途 |
|---|---|
| [WinCraft 平台演进交接包：从当前 0.3 到可组合生态](START_HERE.md) | handoff |
| [执行摘要：让程序长出界面，而不是让宿主长成业务大全](EXECUTIVE_SUMMARY.md) | handoff |
| [如何合入现有仓库，而不覆盖当前工作](INTEGRATION.md) | execution-plan |
| [交给本地 Codex / Luna 的完整执行提示词](LUNA_PROMPT.md) | execution-prompt |

## 产品、设计与实施规范

| 文档 | 用途 |
|---|---|
| [基线、证据与未知边界](docs/00_BASELINE_AND_EVIDENCE.md) | verified-scope |
| [产品哲学与章程](docs/01_CHARTER.md) | user-aligned |
| [生态定位、边界与成功指标](docs/02_PRODUCT_AND_ECOSYSTEM.md) | user-aligned |
| [业界参考：采纳机制，不复制产品](docs/03_REFERENCE_DECISIONS.md) | proposal |
| [架构与代码接线：不重写宿主，不把业务塞进内核](docs/04_ARCHITECTURE.md) | proposal |
| [公共 API、兼容演进与错误语义](docs/05_PUBLIC_API_AND_COMPATIBILITY.md) | proposal |
| [所有权与借用：窗口、组件、状态与高级共享](docs/06_OWNERSHIP.md) | proposal |
| [事件、反应与可撤销资源](docs/07_EVENT_ACTION_LIFECYCLE.md) | proposal |
| [自发现、自适应配置与整合包](docs/08_DISCOVERY_ADAPTIVE_PACKS.md) | proposal |
| [一次性交互：Popup-Ask 与 SysTorch](docs/09_EPHEMERAL_POPUP_SYSTORCH.md) | proposal |
| [主题、国际化与可访问性：从第一批进入架构](docs/10_THEME_I18N_ACCESSIBILITY.md) | proposal |
| [浏览器、TeamSense 与一次性语音](docs/11_BROWSER_TEAMSENSE_VOICE.md) | proposal |
| [多 Harness 状态聚合与人类待办](docs/12_HARNESS_ACTIVITY.md) | proposal |
| [TouchAI 与 PCSense：平台孵化而非功能吞并](docs/13_TOUCHAI_PCSENSE_INCUBATION.md) | proposal |
| [AndroMorph 通知摘要与传输边界](docs/14_ANDROMORPH_TRANSPORT.md) | proposal |
| [原生能力路线：以扩展点验收，不堆 Win32 清单](docs/15_NATIVE_CAPABILITIES.md) | proposal |
| [安全与信任：用户可理解、内核可执行](docs/16_SECURITY.md) | proposal |
| [教程世界与自用：先让人会玩，再让人会写](docs/17_TUTORIAL_DOGFOOD.md) | proposal |
| [下一步路线图：分批形成真实闭环](docs/18_ROADMAP.md) | execution-plan |
| [验证、性能与交付证据](docs/19_VALIDATION_AND_PERFORMANCE.md) | execution-plan |
| [治理、许可、品牌与发布](docs/20_GOVERNANCE_RELEASE_BRAND.md) | user-aligned |
| [文档时效、分层与 Luna 必须遵守的规则](docs/21_DOCUMENTATION_CONTRACT.md) | normative-plan |
| [串起来的用户叙事：从个人工具到可组合环境](docs/22_SCENARIOS.md) | proposal |

## 不同读者

| 文档 | 用途 |
|---|---|
| [用户层：世界、来源与控制权](docs/audience/USER_GUIDE.md) | beginner-design-guide |
| [提供者层：不用前端也能搭建](docs/audience/PROVIDER_GUIDE.md) | provider-design-guide |
| [内核层：不变量比组件数量重要](docs/audience/CORE_GUIDE.md) | core-design-guide |
| [WinCraft evolution handoff — English entry](docs/en/START_HERE.md) | translation-entry |

## 任务、来源与维护

| 文档 | 用途 |
|---|---|
| [供合并进 AGENTS.md 的演进规则](governance/AGENTS_APPENDIX.md) | normative-plan |
| [每批合入审查](governance/REVIEW_CHECKLIST.md) | normative-plan |
| [来源与复核方法](sources/README.md) | evidence-index |
| [需求—规范—任务—验收追踪（生成视图）](plan/TRACEABILITY.md) | generated-view |
| [实施任务与可验收交付（生成视图）](plan/TASKS.md) | generated-view |
| [验收矩阵（生成视图）](plan/ACCEPTANCE.md) | generated-view |
| [提案型契约的使用边界](contracts/README.md) | draft-contract |
| [样例怎么用：先解释，再执行](examples/README.md) | example-guide |
| [交接包自身验证边界](evidence/README.md) | validation-scope |

## 更新计划的单一来源

编辑`plan/tasks.json`的任务定义，再运行`python scripts/render_plan.py --date YYYY-MM-DD`生成追踪/任务/验收视图。验收定义来自任务，实际执行结果存`plan/acceptance.json`，粗粒度推进存`plan/status.json`。代码/基线改变后使用`--reset-results`或逐项重新核验，不能继承旧PASS。最后重新运行包内检查；旧MANIFEST的哈希失效，应为新交付重建。

当前只有12条中英演示资源和英文入口摘要，不宣称40余份中文文档已全量翻译。公众翻译与实际宿主i18n由B02逐步落实。


最终交付状态：[包内验证与下一步](DELIVERY_STATUS.md)。
