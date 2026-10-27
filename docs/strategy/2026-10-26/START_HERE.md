---
{
  "doc_id": "START_HERE",
  "title": "WinCraft 平台演进交接包：从当前 0.3 到可组合生态",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "handoff",
  "audience": "human, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# WinCraft 平台演进交接包：从当前 0.3 到可组合生态

**这是研发与执行交接，不是新版运行时，也不是已实现功能的发布包。**包版本 `strategy-1.0` 与产品版本、线协议版本独立。

本包以用户最后一轮反馈为最高优先级：不封存提供者、不先做 Mod/市场、许可保持不变、国际化前置、保留 Rust/Tauri、应用通过公共 API 使用宿主。已读取的远端基线为 `6929056700b1ba6702288534579debc8a502c139`；本地开始前必须检查 HEAD 漂移。

完整目录：[全包导航](INDEX.md)。

## 最短路径

人类阅读：[执行摘要](EXECUTIVE_SUMMARY.md) → [产品章程](docs/01_CHARTER.md) → [路线图](docs/18_ROADMAP.md)。

Luna 执行：[完整提示词](LUNA_PROMPT.md) → [整合步骤](INTEGRATION.md) → [任务索引](plan/TASKS.md)。从 `B00` 开始，不把全部路线一次合入。

审查覆盖：[需求追踪](plan/TRACEABILITY.md) → [决定账本](plan/decisions.json) → [验收矩阵](plan/ACCEPTANCE.md)。

## 包内三类东西

- **权威约束与计划**：用户决定、架构分层、任务依赖、失败路径、验收、回滚与时效规则。
- **提案型契约**：`contracts/` 与 `examples/` 采用 `draft-2026-10-26`，不是现有宿主接受的新 API。不能直接向协议 0.3 发送这些结构并声称已支持。
- **可执行的规划辅助程序**：离线自检、需求追踪验证、纯数据的自适应配置规划器与测试。它们不启动宿主、不访问用户通知、不安装提供者、不发真实批准。

## 先运行包内检查

```text
python scripts/validate_handoff.py
python -m unittest discover -s tests -v
python scripts/check_repo_baseline.py --repo <WinCraft仓库目录>
```

第一条需要 `jsonschema`；精确依赖见 `requirements-dev.txt`。第三条只读本地 Git，不自动 fetch/reset，也不改变工作区。包内测试通过只证明规划资产一致、示例契约有效，不证明 Windows、浏览器、Android 或各 Harness 的集成成立。

## 为什么没有第二份宿主源码

用户已经有持续演进的公开仓库。本包不再复制旧版源码，避免本地代理用过期交接包覆盖 dev；改动定位见 [代码接线图](docs/04_ARCHITECTURE.md)。实际修改应在用户现有检出上进行。

## 证据与公开边界

[来源注册表](sources/registry.json)包含公开参考及少量受限团队技能的摘要定位；不包含私有源码、令牌或用户业务数据。提交公开仓库前仍须按 [治理与发布](docs/20_GOVERNANCE_RELEASE_BRAND.md)执行资料审查，不自动公开团队私有技能的全文或内部连接信息。
