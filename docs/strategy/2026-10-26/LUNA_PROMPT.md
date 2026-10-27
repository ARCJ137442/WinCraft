---
{
  "doc_id": "LUNA_PROMPT",
  "title": "交给本地 Codex / Luna 的完整执行提示词",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "execution-prompt",
  "audience": "local Codex / Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 交给本地 Codex / Luna 的完整执行提示词

请承接现有 WinCraft 仓库，不重写产品，也不以新一轮问卷替代执行。

## 用户已批准的目标

把 WinCraft 建设为人、程序和 Agent 同台参与的可组合界面运行时。用户最新反馈优先；本包需求与决定账本已汇总。首要工作是稳定公共 API、可拓展内核、声明式界面、权限与生命周期、国际化和可执行文档。Windows悬浮窗是起点，不是最终想象边界。

保持Rust/Tauri、共享托盘宿主、提供者无需前端源码、业务真相外置、运行状态可重建、本机人类接管、读快照与写租约。普通接入不能要求每个应用改Host源码；通用内核/API/native adapter的必要扩展可以做，不是冻结一切源码。

整合包只保存配置、能力需求和适配计划，不保存/保证提供者。导入不自动安装或执行程序；适配代码另行授权，先产计划再校验提交。Mod和官方市场暂不做。许可保持CCOPL及上游署名，不擅自换名或更改归属。WinCraft/WinC为工作称呼，中文名不冻结。

## 先读与重定基线

先读现有AGENTS.md、skills/wincraft-provider/SKILL.md、docs/product/DECISIONS.md、docs/architecture.md、docs/protocol.md和验证摘要；再读本包START_HERE.md、INTEGRATION.md、sources/baseline.json、plan/requirements.json、plan/decisions.json和plan/tasks.json。

本包取证基线：`6929056700b1ba6702288534579debc8a502c139`，线协议0.3。先记录本地HEAD/工作区变化，核查其后新增功能；不能把本包当最新代码快照或覆盖用户工作。仓库记录的测试不是你本轮执行结果。

## 第一轮执行范围

默认按B00开始，然后完成B01/B02中支撑Popup的最小公共能力，交付B03临时提问真实闭环。优先复用现有0.3，不为了Popup提前建设完整插件框架、共享变量系统或市场。若B01某项已有实现，复测后复用。其余路线按依赖逐批推进；到当前执行预算边界时交付已验收纵向成果与下一可执行任务，不谎称全部实现。

Popup来源技能实际名称为`popup-ask`，用户称`popup-question`。定位现有本地技能代码，保持1–4题、2–5选项、自动Other、notes、multiSelect、preview、用户语言与稳定question.id。默认stdout摘要与显式--json返回兼容；关闭/取消/ESC按原语义返回。只替换呈现transport，不能新增提问权限或在本任务中重新向用户弹问卷。

关键：当前`ACTION_TIMEOUT_MS=10000`是普通交互回执，不是人类思考时限。控件动作快速确认，外层问题独立等待/到期/取消，长于10秒仍能完成；连接心跳、关闭、断线、接管、迟到结果与重复提交都有测试。业务副作用不承诺exactly-once，结果不明先读回不盲重试。

## 后续路线必须保留

SysTorch的发起/决策端口；来源风格主题和可信授权区；早期中英和分层文档；受控浏览器桥接、TeamSense、网页聊天与主动语音；动态发现与自适应配置包；组件/子树/状态槽所有权；五类Harness活动面板；外部transport连接的Android通知摘要；TouchAI热键窄闭环与PCSense孵化；教程自用；角色只做原语POC；平台矩阵与正式发布门。具体依赖与用例在tasks/acceptance，不重新复制另一份总计划。

SysTorch/TeamSense现行接口本包未核实：优先本地查，合成fixture可以先行，真实adapter单独BLOCKED，不能借同名仓库、猜endpoint或读真实账户。对OMP/DSH等快速变化来源固定版本与能力，不靠名字推断兼容。

## 工程纪律

1. 每次只认一个规范来源，改动同步模型/Schema/SDK/fixture/文档；旧0.3回归是必需门。
2. i18n、主题、权限、取消、资源清理从第一批进入。主题不能伪装来源，安全模式不是沙箱。
3. 共享可变状态用宿主仲裁/版本CAS和有界事务，不将Arc/Mutex当网络共享内存，不持锁等人或await。
4. 状态推送可合并，用户动作不能静默丢失；事件带身份、因果、版本、交付类别和重同步策略。
5. docs必须带updated_at、last_verified_at、基线、适用协议、状态、来源和读者；翻译源变更标stale。真实运行结果另带环境、命令、退出码和哈希。
6. 假设存在合规工具不代表已经调用；模拟/fixture、Headless、Tauri开发、独立release、真实来源/设备分别报告。
7. 无需向用户反复确认可逆的常规实现；涉及凭据、真实通知/业务写入、设备安装、不可逆操作时遵守原授权。
8. 提交、推送、发布、修改许可证/远程/协作者权限不由本包自动授权。不得开放公网或削弱Origin来让浏览器演示变绿。

## 每批交付格式

更新plan/status.json，提交本地可审阅diff（是否git commit按授权），给出：完成任务ID、实现范围、测试命令/结果、证据级别、文档/翻译更新、真实缺口、回退方式、下一项已满足依赖的任务。失败要留反例，不填造绿色结果。

包内辅助检查（在本包目录）：

```text
python -m pip install -r requirements-dev.txt
python scripts/validate_handoff.py
python -m unittest discover -s tests -v
python scripts/check_repo_baseline.py --repo <WinCraft目录>
```

真正产品验收仍按当前package/Cargo、真实lease_probe和独立Windows release执行。包内规划器通过不等于运行时支持新功能。
