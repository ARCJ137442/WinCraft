---
{
  "doc_id": "INTEGRATION",
  "title": "如何合入现有仓库，而不覆盖当前工作",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "execution-plan",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 如何合入现有仓库，而不覆盖当前工作

## 1. 只读确认

确认目标确实是用户已有 `ARCJ137442/WinCraft` 检出，记录`git status --short`、`git rev-parse HEAD`和remote。不要建立新远程仓库、强制切分支、reset或清理未知文件。冻结基线为`6929056700b1ba6702288534579debc8a502c139`，若当前HEAD更新，阅读差异并把已完成任务标为待复核/已验证，不覆盖回旧实现。

可以运行本包`python scripts/check_repo_baseline.py --repo <路径>`。输出只表示基线与路径关系，不验证代码质量；它不会联网或修改工作区。

## 2. 增量放置

建议把本包文档与plan/contracts/examples工具作为一个独立策略目录放入`docs/strategy/2026-10-26/`。这只是建议的新增位置；保持包内相对结构，避免把本包`START_HERE.md`、`LUNA_PROMPT.md`、`examples/`覆盖仓库同名入口。正式产品Schema/SDK/示例由各任务按现有目录迁入，不能直接把提案型Schema当0.3契约。

根目录`AGENTS.md`只合并`governance/AGENTS_APPENDIX.md`的有用增补；现有授权、安全、开发规则继续有效。`docs/README.md`增加本策略入口。`docs/roadmap.md`保留阶段历史与现有验收，链接本包路线，而不是重复拷贝整份计划。

## 3. 先处理状态，不先改协议号

将本地当前事实写到`plan/status.json`，每项区分NOT_STARTED/IN_PROGRESS/BLOCKED/IMPLEMENTED_UNVERIFIED/VERIFIED。本包的USER_DECIDED只表示方向成立，绝不等于VERIFIED。执行之前不预先改协议版本或自动加新依赖。

## 4. 每批闭环

选择依赖满足的一项任务，先补失败用例，最小修改，跑对应测试，再更新协议/Schema/SDK/文档/翻译与证据。涉及原生窗口就以独立release验收；没有机器时标NOT_RUN而不是用浏览器预览替代。

每一批保留小的可回退改动集，记原HEAD、变更文件与回退方式。不持有源码文件的其他Agent不能并行改同文件。是否建立分支/worktree按当前仓库规则和授权执行，不从“路线全部通过”推断无限发布授权。

## 5. 公开前审阅

P-POPUP私有技能只保留必要接口摘要，不公开原文；来源里私有链接是否对公众暴露另审。公开证据去掉运行描述文件、令牌、真实标题、消息内容、机器账户路径。许可保持原文，中文品牌待定，不自动改仓库归属、包名、商标或协作者权限。

本包不修改远程。用户未来授权推送时，在当前已有仓库内完成最小提交并回读远程；公开发行仍需独立release门。
