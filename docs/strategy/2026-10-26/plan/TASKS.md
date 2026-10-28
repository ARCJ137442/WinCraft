---
{
  "doc_id": "plan__TASKS",
  "title": "实施任务与可验收交付（生成视图）",
  "updated_at": "2026-10-28",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "generated-view",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 实施任务与可验收交付（生成视图）

从tasks.json生成。状态不是已通过的证据。
| 任务 | 标题 | 依赖 | 验证层 |
|---|---|---|---|
| B00-01 | 重定基线与旧链路回归 | 无 | L0-L4 |
| B00-02 | 合并需求账本与文档时效规则 | B00-01 | L0 |
| B00-03 | 参考对象与来源身份复核 | B00-01 | L0 |
| B00-04 | 形成首轮风险与执行状态板 | B00-02, B00-03 | L0 |
| B01-01 | 版本与能力契约演进门 | B00-04 | L1-L2 |
| B01-02 | 会话注册与可撤销资源生命周期 | B01-01 | L1-L2 |
| B01-03 | 授权inventory与发现契约 | B01-01, B01-02 | L1-L2 |
| B01-04 | 公共场景SDK与诊断一致性 | B01-01, B01-02 | L1-L2 |
| B02-01 | 国际化基础与三层术语 | B00-02, B01-01 | L1-L4 |
| B02-02 | 主题token与可信界面边界 | B02-01, B01-04 | L1-L4 |
| B02-03 | 教程世界与管理器自用 | B02-01, B02-02 | L1-L4 |
| B02-04 | 原生可访问性与输入回归 | B02-03 | L3-L4 |
| B03-01 | Popup兼容适配与请求状态机 | B01-04, B02-01 | L1-L2 |
| B03-02 | Popup真实临时世界闭环 | B03-01, B02-02 | L2-L5 |
| B03-03 | SysTorch发起与决策端口 | B03-02 | L0-L5 |
| B03-04 | 首个可交付版本与上游契约回归 | B03-02, B03-03, B02-04 | L2-L5 |
| B04-01 | 有类型事件订阅与交付类别 | B01-02, B01-04 | L1-L2 |
| B04-02 | 窗口行为与焦点意图 | B04-01 | L1-L4 |
| B04-03 | 授权快捷键资源 | B01-02, B04-01 | L1-L4 |
| B04-04 | TouchAI窄用例与等价性清单 | B04-03, B02-02 | L2-L5 |
| B05-01 | 浏览器Native Messaging桥接 | B01-03, B01-04 | L1-L5 |
| B05-02 | TeamSense只读在线服务投影 | B05-01 | L0-L5 |
| B05-03 | 网页聊天语义对象与动作边界 | B05-01, B03-02 | L1-L5 |
| B05-04 | 主动语音输入与朗读POC | B05-03, B02-04 | L3-L5 |
| B06-01 | 配置包格式与无秘密导出 | B01-03, B02-02 | L1-L2 |
| B06-02 | 纯规划器与有界环境适配 | B06-01 | L0-L2 |
| B06-03 | 计划预览、提交与回退 | B06-02, B01-02 | L1-L4 |
| B06-04 | 配置分享与新机器验收 | B06-03 | L0-L5 |
| B07-01 | 资源树与单写子树租约 | B01-02, B01-04 | L1-L2 |
| B07-02 | 结构事务、父子撤销与过滤 | B07-01 | L1-L2 |
| B07-03 | 类型状态槽与受控共享高级通道 | B07-02 | L1-L2 |
| B07-04 | 多来源组合性质与真实窄验收 | B07-02, B07-03 | L1-L5 |
| B08-01 | 统一活动模型与只读聚合器 | B01-03, B01-04 | L1-L2 |
| B08-02 | 两类真实Harness先行适配 | B08-01, B00-03 | L2-L5 |
| B08-03 | 扩到五类并作组件级组合 | B08-02, B07-04 | L1-L5 |
| B08-04 | 决策卡与官方批准回传 | B08-02, B03-04 | L2-L5 |
| B09-01 | 设备消息信封与外部传输端口 | B01-03, B08-01 | L1-L2 |
| B09-02 | Android通知摘要单设备验证 | B09-01, B00-03 | L5-L6 |
| B09-03 | 手机与Agent待办合并呈现 | B09-02, B08-01 | L1-L6 |
| B09-04 | 多通道故障与隐私验收 | B09-03 | L1-L6 |
| B10-01 | PCSense孵化窄原型 | B06-04, B07-04 | L2-L5 |
| B10-02 | 毕业与可移植性演练 | B10-01 | L0-L5 |
| B10-03 | 窗口组与角色可能性最小POC | B04-02, B06-03 | L1-L4 |
| B10-04 | 独立创作者验证与外部参考更新 | B10-01, B06-04, B02-03 | L5 |
| B11-01 | 持续兼容与资源性能基线 | B03-04, B02-04 | L1-L5 |
| B11-02 | Windows发布前原生验收 | B11-01, B02-04 | L4-L5 |
| B11-03 | macOS/Linux能力矩阵与受限试构建 | B01-01, B11-01 | L6 |
| B11-04 | 集体治理与公众发布准备 | B11-02, B00-02 | L0-L6 |

## B00-01 · 重定基线与旧链路回归

**前置：** 无；**需求：** R002, R003, R061, R062, R064

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `AGENTS.md`；`docs/engineering/VALIDATION.md`；`Cargo.toml`；`package.json`

### 实施
1. 记录git status、HEAD和与冻结SHA的差异；不重置他人修改
2. 读当前AGENTS和Provider Skill，确认0.3及近期已完成工作
3. 运行本机现有UI、Rust、协议测试，分离历史报告和本轮结果

### 验收
- **B00-01-A1** 基线/锁文件/环境可复现且未覆盖工作区
- **B00-01-A2** 旧链路实际结果逐项记录；无环境维持NOT_RUN
- **B00-01-A3** 已有功能不重复立项

**验证层/目录：** L0-L4 / current WinCraft checkout

```text
git status --short
git rev-parse HEAD
npm run check
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 本任务原则上只读；仅撤销新增证据索引，不改已有测试记录。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B00-02 · 合并需求账本与文档时效规则

**前置：** B00-01；**需求：** R029, R030, R043, R048, R062, R070

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `AGENTS.md`；`docs/product/DECISIONS.md`；`proposed: docs/strategy/2026-10-26/`

### 实施
1. 按INTEGRATION增量放入本包，保留旧决定历史
2. 将AGENTS_APPENDIX审阅合并，不覆盖旧权限
3. 生成中英术语入口、日期/来源/状态检查并纳入离线检查

### 验收
- **B00-02-A1** 每条需求可追到owner_doc/任务/用例
- **B00-02-A2** 无许可、仓库归属或技术名称变更
- **B00-02-A3** 私有技能摘要进入公开提交前被单独审查

**验证层/目录：** L0 / handoff root

```text
python scripts/validate_handoff.py
python -m unittest discover -s tests -v
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 移除本次增补段与新增目录；不回滚原AGENTS其他作者修改。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B00-03 · 参考对象与来源身份复核

**前置：** B00-01；**需求：** R041, R063, R071

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: docs/research/integration-source-lock.json`

### 实施
1. 锁定popup-ask、DSH、TouchAI、各Harness版本与入口
2. 将 SysTorch 标记为本地未发行 M1 候选并固定相关文件哈希；将 TeamSense 标记未定位，不采用同名仓库推断
3. 补官方API、权限、许可证边界的来源索引及复核触发器

### 验收
- **B00-03-A1** 来源身份/版本/核验日期可查
- **B00-03-A2** 未核实接口不会出现在真实集成PASS列表
- **B00-03-A3** 第三方文档的可用性不等于本机已经安装

**验证层/目录：** L0 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 保留旧来源记录，仅废弃错误的新锁定条目。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B00-04 · 形成首轮风险与执行状态板

**前置：** B00-02, B00-03；**需求：** R061, R064, R070

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: docs/strategy/2026-10-26/plan/status.json`

### 实施
1. 将任务初始状态与当前仓库差异对齐
2. 明确本轮只推进B01/B02最小依赖和B03闭环
3. 将权限、原生环境和第三方接口缺口列为局部阻塞

### 验收
- **B00-04-A1** 每个阻塞有范围/解除条件且不阻塞无关任务
- **B00-04-A2** 不把路线批准转成远程推送/真实数据读取授权

**验证层/目录：** L0 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 恢复任务状态文件到前一评审版；不删除已收集证据。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B01-01 · 版本与能力契约演进门

**前置：** B00-04；**需求：** R001, R004, R042, R051, R059

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `crates/wincraft-core/src/model.rs`；`crates/wincraft-server/src/hub.rs`；`protocol/`；`examples/python/client.py`

### 实施
1. 审查strict0.3与deny_unknown_fields，制定兼容ADR
2. 稳定必选核心，可选特性用命名能力和schema版本表达
3. 新增SDK查询/错误分支与旧0.3 fixture，不直接让旧客户端忽略未知结构

### 验收
- **B01-01-A1** 旧0.3客户端通过原路径工作或收到明确且有文档的迁移错误
- **B01-01-A2** 协商未支持能力不伪成功
- **B01-01-A3** 新增可选能力不意外赋权

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 关闭新能力并恢复旧握手入口；保留可诊断错误。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B01-02 · 会话注册与可撤销资源生命周期

**前置：** B01-01；**需求：** R005, R007, R040, R041, R053, R065

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `crates/wincraft-core/src/engine.rs`；`crates/wincraft-server/src/hub.rs`

### 实施
1. 建立资源注册/撤销/清理统一路径，复用现有会话与epoch
2. 资源绑定身份、scope、授权与生命周期
3. 断线、父资源撤销、operator hold时有序释放订阅与动作

### 验收
- **B01-02-A1** 重复撤销幂等且不影响其他session
- **B01-02-A2** 新会话不能复用旧资源句柄
- **B01-02-A3** 注册/撤销不会执行第三方宿主代码

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 撤销新资源类型并回到现有世界级租约；不恢复已撤销的旧权限。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B01-03 · 授权inventory与发现契约

**前置：** B01-01, B01-02；**需求：** R020, R024, R045, R065

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `crates/wincraft-server/src/hub.rs`；`proposed: protocol/provider-inventory.schema.json`

### 实施
1. 把发现元数据与world加入/读写授权分离
2. 声明来源类型/能力/实例/版本/在线与数据新鲜度
3. 仅对批准的端点和已注册来源发现，不扫描浏览器账号或全部进程

### 验收
- **B01-03-A1** 发现结果不包含token/lease/完整业务数据
- **B01-03-A2** 相同显示名的两个实例不会合并
- **B01-03-A3** offline/stale/unauthorized可区分

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 停止新发现入口，旧descriptor与hello不变。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B01-04 · 公共场景SDK与诊断一致性

**前置：** B01-01, B01-02；**需求：** R006, R052, R059, R071

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `examples/python/client.py`；`protocol/`；`skills/wincraft-provider/`；`scripts/check_contracts.py`

### 实施
1. 统一请求关联、版本冲突、取消、数据新鲜度与能力降级示例
2. 正反场景覆盖replace/patch/data/action
3. 给错误码加稳定机器ID与可本地化文案，文档不成为第二份协议

### 验收
- **B01-04-A1** 同一fixture在Schema/SDK/真实服务结果一致
- **B01-04-A2** 动态操作保持未修改节点身份与输入草稿
- **B01-04-A3** 错误日志不包含凭据或业务正文

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 保持原client.py兼容入口，新辅助API可撤回而旧调用不变。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B02-01 · 国际化基础与三层术语

**前置：** B00-02, B01-01；**需求：** R029, R031, R032, R048, R069

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `apps/desktop/src/`；`crates/wincraft-server/src/self_provider.rs`；`proposed: locales/`

### 实施
1. 提取宿主文案，中英键集和参数一致
2. 权限/错误/教程文本本地化，机器ID不翻译
3. 文档按用户/Provider/内核层表达同一快照和租约模型

### 验收
- **B02-01-A1** 缺失翻译回退且标记，布局无溢出
- **B02-01-A2** 协议ID/操作名在语言切换后稳定
- **B02-01-A3** 原始用户文本不被自动翻译

**验证层/目录：** L1-L4 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 回退默认中文资源但保持稳定键；不得把显示文案重新硬编码进协议。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B02-02 · 主题token与可信界面边界

**前置：** B02-01, B01-04；**需求：** R012, R032, R049

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `apps/desktop/style.css`；`apps/desktop/src/renderer.ts`；`proposed: protocol/theme.schema.json`

### 实施
1. 实现有限颜色/字号/间距/圆角token和预设
2. 明确宿主安全区域、用户无障碍偏好优先于提供者主题
3. 主题解析禁止CSS/JS/远程可执行资源，超界值拒绝

### 验收
- **B02-02-A1** 来源风格可表达且不能伪装系统授权条
- **B02-02-A2** 高对比/放大/减少动画生效
- **B02-02-A3** 无效主题回退，不影响租约或数据

**验证层/目录：** L1-L4 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 切回默认主题并释放主题资源；不删除用户主题文件。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B02-03 · 教程世界与管理器自用

**前置：** B02-01, B02-02；**需求：** R001, R035, R050

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `crates/wincraft-server/src/self_provider.rs`；`apps/desktop/src/renderer.ts`；`skills/wincraft-provider/`

### 实施
1. 五课以通用组件和普通交互创建教学世界
2. 管理器和教程复用同一renderer，operator特权仍局部可信
3. 退出只清理教程资源，允许跳过

### 验收
- **B02-03-A1** 新用户可完成建窗/改字/按钮/主题/发现课程
- **B02-03-A2** 教程fixture不接真实用户数据
- **B02-03-A3** 外部Provider不能冒充内部管理器取得operator权限

**验证层/目录：** L1-L4 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 关闭教程入口，管理器正常可用；只清理教学标记资源。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B02-04 · 原生可访问性与输入回归

**前置：** B02-03；**需求：** R032, R035

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `apps/desktop/src/renderer.ts`；`tests/`；`proposed: evidence/local/a11y/`

### 实施
1. 明确角色/名称/状态/键盘顺序与IME保护
2. 独立release检查UIA树及真实键盘/鼠标/读屏路径
3. 记录中英长文本、高DPI、窄窗和内部滚动

### 验收
- **B02-04-A1** 可只用键盘提交并取消，不困住焦点
- **B02-04-A2** 来源更新不打断IME或覆盖草稿
- **B02-04-A3** DOM通过不替代UIA和原生验收

**验证层/目录：** L3-L4 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 回退有问题的样式/组件变化，保留旧输入行为。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B03-01 · Popup兼容适配与请求状态机

**前置：** B01-04, B02-01；**需求：** R008, R009, R010, R064

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `examples/python/popup_ask_provider.py`；`skills/wincraft-provider/references/popup-ask.md`

### 实施
1. 先复用现有validate-only和返回序列化，不在WinCraft复制第二份题目业务
2. 适配question.id、选项、Other、notes、多选、preview
3. 为外层request建立独立等待/成功/取消/错误状态和到期规则

### 验收
- **B03-01-A1** 原输入正反fixture一致；默认stdout摘要、--json结构不变
- **B03-01-A2** 关闭/ESC/取消按原reason返回，不当error
- **B03-01-A3** 普通10秒action ack不终止等待人类的问题

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 显式回到既有popup transport；不得同时显示两个问题窗口。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B03-02 · Popup真实临时世界闭环

**前置：** B03-01, B02-02；**需求：** R008, R009, R010, R066, R073

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `examples/python/popup_ask_provider.py`；`apps/desktop/src/renderer.ts`；`crates/wincraft-core/src/scene.rs`；`crates/wincraft-core/src/engine.rs`；`apps/desktop/src-tauri/src/main.rs`；`tests/test_popup_ask_provider.py`；`docs/strategy/2026-10-26/docs/09_EPHEMERAL_POPUP_SYSTORCH.md`；`skills/wincraft-provider/references/popup-ask.md`

### 实施
1. 用声明式选项组和textarea收集选择与备注；方向键/Tab保留可访问路径，Ctrl+Enter带草稿提交
2. 本地点击及时ack，整体提交产生一个终态结果；成功后销毁本次临时世界
3. 仅保存本机窗口几何偏好，下一次创建新世界/新租约并复用位置；不保存答案或旧world id
4. 断线/租约失效/用户接管时停写并安全关闭或标记，清理世界
5. 在连接Host/创建世界之前占用一个per-user-session Popup槽；并发调用返回busy并指向世界管理器，不创建第二个窗口或抢焦点。

### 验收
- **B03-02-A1** 成功/取消/窗口关闭/来源退出/宿主退出均有确定结果或明确未知结果
- **B03-02-A2** 同一请求不因重试重复提交业务
- **B03-02-A3** 并发多个问题有配额与可发现入口，不强抢焦点
- **B03-02-A4** 成功提交销毁本次临时世界；下一次请求以新world与lease复用最近一次可读的原生位置/尺寸，未观测位置不得猜测
- **B03-02-A5** 选择后Tab直接进入备注；Ctrl+Enter连同当前备注草稿提交，方向键/读屏仍能完成选项操作

**验证层/目录：** L2-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 停止WinCraft transport并回退旧实现；清理自身世界不动其他人世界。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B03-03 · SysTorch发起与决策端口

**前置：** B03-02；**需求：** R011, R012, R063

**输入：** 本地发现 SysTorch（原 Jev Switch）M1 决策 API 候选；相关服务模块、存储模块与契约在来源工作树中仍未提交/未发行。B03-02 仍是前置；真实运行时需显式来源地址和受管理 caller token。

**定位：** `proposed: examples/integrations/systorch/`；`proposed: docs/integrations/systorch.md`

### 实施
1. 分离发起与回答权限：caller 可创建/读取/取消自己的任务；回答仅归 SysTorch local-owner，WinCraft 不传 owner 密钥、不调用 answers 写接口
2. 基于通用 renderer 建立显式发起、只读追踪/结果展示和显式取消；关闭 WinCraft 窗口不取消来源任务
3. 地址显式配置；仅允许 loopback HTTP 或 HTTPS/安全隧道；用本地合成HTTP服务验证状态码、幂等、权限、重定向与超时边界
4. 待 B03-02 完成且用户提供实际运行时地址与受管理 caller token 后，才验证当前 SysTorch M1 候选的真实连接

### 验收
- **B03-03-A1** 发起和批准不互相混用，参数/权限单独校验
- **B03-03-A2** 只有合成fixture时明确标mock
- **B03-03-A3** 真实API未定位只阻塞真实适配不阻塞通用交互

**验证层/目录：** L0-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 撤销该Provider注册；任务真相留SysTorch。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B03-04 · 首个可交付版本与上游契约回归

**前置：** B03-02, B03-03, B02-04；**需求：** R009, R010, R061, R064

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `tests/`；`proposed: docs/integrations/popup-compatibility.md`

### 实施
1. 固定popup输入/输出golden cases和中文编码通道
2. 长等待、超时、重连、迟到结果与清理压力测试
3. 交付一条真实成功与一条取消链路，记录所有未测路径

### 验收
- **B03-04-A1** 兼容层不改变既有Skill启用和提问权限
- **B03-04-A2** 实际release等待超10秒仍可提交
- **B03-04-A3** 上游契约未核验部分保持BLOCKED而非猜测

**验证层/目录：** L2-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 回退适配层功能开关，保留旧Popup路径。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B04-01 · 有类型事件订阅与交付类别

**前置：** B01-02, B01-04；**需求：** R052, R053

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `crates/wincraft-core/src/model.rs`；`crates/wincraft-server/src/hub.rs`；`protocol/`

### 实施
1. 按快照sequence建立类型事件，明确cause/source/window_revision
2. 把可合并状态与不可静默丢弃交互分开
3. 设计取消订阅、重同步、慢消费者和因果循环预算

### 验收
- **B04-01-A1** 高频几何可合并到最新态，不能承诺每帧不丢
- **B04-01-A2** 读者订阅不会取得写权
- **B04-01-A3** 慢消费者重同步/断开可解释，重复事件不循环触发动作

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo fmt --all -- --check
cargo test --workspace
cargo check --workspace
cargo clippy --workspace --all-targets -- -D warnings
python -m unittest discover -s tests -v
python examples/python/lease_probe.py --runtime <actual headless descriptor>
```

**说明：** 保留事件类型、权限、队列合并与取消的专用正反测试；以真实 headless WebSocket lease_probe 覆盖订阅与慢消费者；状态订阅只观察已加入世界；不自动执行动作。真实 Tauri 像素行为不属于本任务验收

**回滚：** 停新订阅API，回到已有快照推送；不更改0.3快照意义。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B04-02 · 窗口行为与焦点意图

**前置：** B04-01；**需求：** R054, R055

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `apps/desktop/src-tauri/src/windows.rs`；`apps/desktop/src-tauri/src/main.rs`；`crates/wincraft-core/src/scene.rs`；`crates/wincraft-core/src/engine.rs`；`crates/wincraft-server/src/hub.rs`；`protocol/scene.schema.json`；`protocol/request.schema.json`；`protocol/methods.json`；`examples/python/obsidian-workspace.py`；`skills/wincraft-provider/`

### 实施
1. 以工作区锚定/边距和有限运动为首个行为
2. 坐标/DPI/人类交接在宿主本地处理
3. 焦点请求与置顶/显隐分开并返回原生结果
4. 增加能力门控的宿主原生窗口动作 allowlist；用户点击后由宿主执行现存窗口 activate/maximize/restore/minimize，不传任意进程路径或代码。

### 验收
- **B04-02-A1** 切显示器/DPI变化后位置可恢复
- **B04-02-A2** 用户接管立即停自动运动
- **B04-02-A3** Windows拒绝前台激活时返回明确失败，不能把系统不允许的 SetForegroundWindow 报成成功。
- **B04-02-A4** 仅原生host宣告 external_window_actions；应用ID/操作/title filter严格allowlist且有界；headless拒绝，disabled/stale/revoked按钮不执行
- **B04-02-A5** 真实Tauri用户点击Obsidian Workspace标题激活既有匹配Obsidian窗口，不启动新进程；动作失败向用户显示失败并且不向provider伪造成功回执

**验证层/目录：** L1-L4 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 取消行为句柄，恢复用户可拖动窗口和管理器救援。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B04-03 · 授权快捷键资源

**前置：** B01-02, B04-01；**需求：** R018, R066

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `apps/desktop/src-tauri/src/main.rs`；`proposed: crates/wincraft-core/src/shortcuts.rs`

### 实施
1. 核对当前Tauri依赖后选择兼容插件或薄原生适配
2. 按session/scope登记快捷键；冲突/保留键/撤销明确
3. 本机用户授权与一键停用，无后台键盘记录

### 验收
- **B04-03-A1** 冲突注册失败不占用他人热键
- **B04-03-A2** 断线/撤销/退出后无残留绑定
- **B04-03-A3** IME/输入框/平台组合键不被默认破坏

**验证层/目录：** L1-L4 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 卸载本批注册的热键并恢复旧入口；不修改系统全局配置。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B04-04 · TouchAI窄用例与等价性清单

**前置：** B04-03, B02-02；**需求：** R018, R050

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: examples/integrations/touchai/`；`proposed: docs/integrations/touchai-gap-matrix.md`

### 实施
1. 由用户确认正确项目后列热键/输入/结果/上下文等功能矩阵
2. 只实现召唤→输入→来源返回→隐藏闭环
3. 文件/屏幕/剪贴板权限留原提供者，缺口单列

### 验收
- **B04-04-A1** 可以复现一项实际工作流而非只弹空窗
- **B04-04-A2** 无法实现的功能不标等价
- **B04-04-A3** 不复制未审许可源码进Host

**验证层/目录：** L2-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 停Provider与热键资源，TouchAI原生界面继续工作。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B05-01 · 浏览器Native Messaging桥接

**前置：** B01-03, B01-04；**需求：** R014, R016, R065

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: integrations/browser-extension/`；`proposed: tools/browser-native-bridge/`

### 实施
1. 建立扩展ID白名单与严格消息Schema
2. 桥接自己保管descriptor/host token，网页只能有限语义请求
3. 内容脚本权限按站点/用户动作授予，关闭页/重连可诊断

### 验收
- **B05-01-A1** 任意网页不能拿到token或直接调用Host
- **B05-01-A2** 保留现有Origin拒绝策略
- **B05-01-A3** 桥接断开后来源stale而非继续显示实时

**验证层/目录：** L1-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 注销本次注册的消息宿主/扩展配置；不删浏览器账号或历史。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B05-02 · TeamSense只读在线服务投影

**前置：** B05-01；**需求：** R013, R063

**输入：** TeamSense现行仓库/API与授权须本地核对；本包未定位。

**定位：** `proposed: examples/integrations/teamsense/`；`proposed: contracts/usage-observation.schema.json`

### 实施
1. 在本地定位真实API/身份/数据口径，优先API其次明确DOM适配
2. 将服务器负载与quota分开建字段，带单位/更新时间/来源
3. 未提供官方总额度时标unknown或estimate，不推导伪余额

### 验收
- **B05-02-A1** 账号/提供商/窗口期不同数据不混算
- **B05-02-A2** 数据过期和断线清晰
- **B05-02-A3** 真实接口未定位时只有合成演示，不改TeamSense

**验证层/目录：** L0-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 停只读Provider；Host与服务无业务修改。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B05-03 · 网页聊天语义对象与动作边界

**前置：** B05-01, B03-02；**需求：** R014, R025

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: integrations/browser-extension/adapters/`；`proposed: docs/integrations/web-chat.md`

### 实施
1. 区分原标签页语义投影、API独立会话、视觉裁剪三种模式
2. 先只读选定会话摘要/状态，再显式发送用户确认输入
3. 站点限制、DOM变化、登录失效保留错误；不复制cookie或绕过登录/反自动化

### 验收
- **B05-03-A1** 不承诺任意网页一键变原生APP
- **B05-03-A2** 页面关闭/导航后错误地绑定旧对话被拒绝
- **B05-03-A3** 用户发送内容有可见预览和回执，无法验证时返回unknown

**验证层/目录：** L1-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 禁用站点适配器；保留原浏览器会话和数据。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B05-04 · 主动语音输入与朗读POC

**前置：** B05-03, B02-04；**需求：** R015, R032, R066

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `apps/desktop/src-tauri/`；`proposed: docs/poc/voice.md`

### 实施
1. 选定平台API先做原生POC，说明离线/在线处理和语言能力
2. 明确录音指示、时限、取消和设备丢失
3. 先确认识别文本再交提供者，不把原始音频广播

### 验收
- **B05-04-A1** 未授权时没有麦克风活动
- **B05-04-A2** 取消/设备失联后释放资源
- **B05-04-A3** 识别结果不自动成为系统命令或批准

**验证层/目录：** L3-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 禁用语音能力并回到文本输入；删除仅属测试的临时音频。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B06-01 · 配置包格式与无秘密导出

**前置：** B01-03, B02-02；**需求：** R019, R022, R033, R040, R072

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: protocol/pack.schema.json`；`proposed: tools/pack/`

### 实施
1. 定义能力需求、蓝图/主题引用、可选依赖与适配声明
2. 限制路径/大小/文件类型，manifest不接受credential或install hook
3. 无凭据导出，版本校验与迁移明确

### 验收
- **B06-01-A1** 包不包含提供者二进制/descriptor/lease
- **B06-01-A2** 缺少Provider是可解释需求而非安装指令
- **B06-01-A3** 读取恶意路径/未知字段失败且未执行文件

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 关闭包导入入口，原世界不受影响。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B06-02 · 纯规划器与有界环境适配

**前置：** B06-01；**需求：** R020, R021, R067

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: crates/wincraft-core/src/plans.rs`；`examples/adapter/adaptive_plan.py`

### 实施
1. 从批准的inventory生成确定性计划，先不调用Host
2. 按版本/能力/权限/在线/新鲜度选择，歧义交用户
3. 适配程序独立授权运行只产候选计划，再由宿主校验，不在import执行

### 验收
- **B06-02-A1** 同输入同计划，缺失必选block/可选degrade
- **B06-02-A2** 两个同等来源不会任意选一个
- **B06-02-A3** 适配程序不能通过计划扩大权限或读取全机

**验证层/目录：** L0-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 丢弃未执行计划；规划不应产生外部副作用。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B06-03 · 计划预览、提交与回退

**前置：** B06-02, B01-02；**需求：** R022, R067, R072

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `crates/wincraft-server/src/hub.rs`；`crates/wincraft-server/src/self_provider.rs`

### 实施
1. 计划携带inventory版本和用户确认，执行前重验
2. 建立本次创建资源账本，失败只清理本次资源
3. 明确布局覆盖优先级和抖动抑制，不宣称多窗口OS事务原子

### 验收
- **B06-03-A1** 环境变化使旧计划失效并重新规划
- **B06-03-A2** 导入取消不会清空既有世界
- **B06-03-A3** 失败报告部分成功与清理结果，不造假回滚

**验证层/目录：** L1-L4 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 按本次资源账本释放新增资源；不恢复旧epoch或覆盖用户后续修改。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B06-04 · 配置分享与新机器验收

**前置：** B06-03；**需求：** R019, R020, R033, R050, R070

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: examples/packs/`；`docs/`；`skills/wincraft-provider/`

### 实施
1. 提供有全来源/缺可选/缺必选/权限不足四份环境fixture
2. 两个独立用户环境只复用配置并重新授权
3. 记录分享格式，不建官方安装市场或社区网站

### 验收
- **B06-04-A1** 没有预装Provider的新机器不会自动运行下载代码
- **B06-04-A2** 分享内容不含原机路径/密钥/私有标题
- **B06-04-A3** 使用者可解释每个缺失区域及其替代方案

**验证层/目录：** L0-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 删除合成导入世界和测试包，保留用户来源安装。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B07-01 · 资源树与单写子树租约

**前置：** B01-02, B01-04；**需求：** R005, R026, R027, R069

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `crates/wincraft-core/src/model.rs`；`crates/wincraft-core/src/engine.rs`；`protocol/`

### 实施
1. 先建立world authority、component subtree、data namespace的区分
2. 窗口级租约作为兼容模式，子树唯一写者、读者为快照
3. 引入资源generation和局部revision，不用全世界revision制造无关冲突

### 验收
- **B07-01-A1** 两个不相交子树可独立更新
- **B07-01-A2** 旧0.3整窗writer与子树writer模式不可非法混用
- **B07-01-A3** 读者不能取得可写别名或其他scope私有数据

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 新世界退回整窗独占模式；禁止把活动子树写者静默合并。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B07-02 · 结构事务、父子撤销与过滤

**前置：** B07-01；**需求：** R007, R028, R065

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `crates/wincraft-core/src/scene.rs`；`crates/wincraft-core/src/engine.rs`；`crates/wincraft-server/src/hub.rs`

### 实施
1. 校验insert/remove/move/replace所触及的所有资源
2. 父删除前处理子租约撤销，旧消息fence
3. 快照在服务端按read scope过滤，不全发再前端隐藏

### 验收
- **B07-02-A1** 不能把无权节点移动进自有子树偷取
- **B07-02-A2** 跨子树失败整批不部分提交
- **B07-02-A3** 父撤销后任何旧子lease写入被拒绝

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 停止新子树操作，保留最后合法快照与撤销状态。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B07-03 · 类型状态槽与受控共享高级通道

**前置：** B07-02；**需求：** R026, R027, R028

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: crates/wincraft-core/src/state_slots.rs`；`protocol/`

### 实施
1. 共享从类型槽和版本CAS开始，不开放任意全局JSON可写引用
2. 必要共享以宿主仲裁队列/短事务声明，不持锁await/等人
3. 限制循环引用、跨scope引用、撤销后读取和配额

### 验收
- **B07-03-A1** 竞争CAS一方失败可诊断且无丢失更新
- **B07-03-A2** Arc式共享不绕过权限与可变规则
- **B07-03-A3** 慢或崩溃参与者不会锁住整个UI

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 关闭高级共享能力，普通独占槽和子树保持工作。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B07-04 · 多来源组合性质与真实窄验收

**前置：** B07-02, B07-03；**需求：** R006, R026, R028, R061

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `crates/wincraft-core/tests/`；`examples/python/`；`proposed: tests/ownership/`

### 实施
1. 加入随机操作/撤销/乱序/断线性质测试
2. 先用合成来源验证不相交写，再选两个已授权真实来源
3. 窗口几何仍由单authority控制，不以多个组件owner争坐标

### 验收
- **B07-04-A1** 多写者只在互不重叠权限域成立
- **B07-04-A2** 任何序列不产生无owner可变资源
- **B07-04-A3** 真实来源失败不会改变其他区域业务状态

**验证层/目录：** L1-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 停止组合Provider，恢复独立世界；各来源业务数据不迁移。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B08-01 · 统一活动模型与只读聚合器

**前置：** B01-03, B01-04；**需求：** R023, R024, R025, R059

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: examples/integrations/agent-board/`；`proposed: protocol/activity.schema.json`

### 实施
1. 定义source/instance/session/parent/task/source_status/normalized_status/freshness
2. unknown/stale与idle分开，来源计数不双重计父子
3. 先单聚合Provider占窗，后续子树writer模式标明

### 验收
- **B08-01-A1** 断线不是任务完成或空闲
- **B08-01-A2** 模型名/显示名不作身份
- **B08-01-A3** 只读面板没有批准/写文件/继续执行权限

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 停聚合器并释放世界，原Harness继续运行。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B08-02 · 两类真实Harness先行适配

**前置：** B08-01, B00-03；**需求：** R023, R024, R071

**输入：** 本地已安装Harness及用户选定会话/端点；不能自动读取所有session日志。

**定位：** `proposed: examples/integrations/agent-board/adapters/`

### 实施
1. 先选择本地确实存在的两种Harness，固定其API版本
2. 优先官方事件/SDK，文件解析仅显式授权且记录脆弱性
3. 重新启动/多实例/子会话的发现离开重建测试

### 验收
- **B08-02-A1** 两种真实来源可同看且来源证据分开
- **B08-02-A2** 不把全部任意既有CLI会话假定可枚举
- **B08-02-A3** 适配失败仅对应来源stale

**验证层/目录：** L2-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 卸载适配注册/停只读进程，不改Harness配置和业务会话。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B08-03 · 扩到五类并作组件级组合

**前置：** B08-02, B07-04；**需求：** R023, R024, R026

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: examples/integrations/agent-board/adapters/`；`skills/wincraft-provider/`

### 实施
1. 补Claude/Codex/OpenCode/DSH/omp能力与版本矩阵，缺者保留NOT_RUN
2. 两种已验证来源切为独立子树写入者
3. 各自重连/离线不争整窗lease或删除别人的卡片

### 验收
- **B08-03-A1** 五类都有明确入口/未知边界，不伪造五种实测
- **B08-03-A2** 至少两种真实独立writer并发验收
- **B08-03-A3** 动作路由跟随组件owner，不被后加入者截获

**验证层/目录：** L1-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 回到只读聚合器单writer模式；不更改来源任务。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B08-04 · 决策卡与官方批准回传

**前置：** B08-02, B03-04；**需求：** R025, R010, R066

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: examples/integrations/agent-board/decisions/`

### 实施
1. 只对确认支持的Harness建立approval adapter
2. 问题绑定source/session/request/digest/expiry，结果回原权威端
3. 撤销/过期/已在别处处理时阻止二次批准

### 验收
- **B08-04-A1** 显示任务不自动具备批准权限
- **B08-04-A2** 批准前显示具体操作与来源，token不在卡片中
- **B08-04-A3** 网络超时只读回结果，不盲重放副作用

**验证层/目录：** L2-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 禁用批准通道，面板退回只读状态。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B09-01 · 设备消息信封与外部传输端口

**前置：** B01-03, B08-01；**需求：** R036, R037, R038, R065

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: protocol/device-message.schema.json`；`proposed: examples/integrations/device-inbox/`

### 实施
1. 定义origin device/source seq/message id/TTL/provenance/redaction
2. 只消费外部transport提供的认证通道
3. 本地合成乱序/重复/过期/撤销测试，不建多跳网络

### 验收
- **B09-01-A1** 重复消息不增加待办数
- **B09-01-A2** 过期/撤销内容不继续可操作
- **B09-01-A3** 网络中继声明不自动成为来源身份

**验证层/目录：** L1-L2 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 停收本端口，保留来源数据不变。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B09-02 · Android通知摘要单设备验证

**前置：** B09-01, B00-03；**需求：** R036, R039

**输入：** 用户明确选择的真机、通知权限和来源；无条件时停在合成信封。

**定位：** `AndroMorph provider boundary (separate project)`；`proposed: examples/integrations/device-inbox/`

### 实施
1. 核实AndroMorph实际通知能力与授权，不继承旧fixture PASS
2. 由用户选应用/时段，优先只读和脱敏摘要
3. 通过一个已存在授权通道传递，设备取消后撤销呈现

### 验收
- **B09-02-A1** 未授权应用通知不被读取或上传
- **B09-02-A2** 摘要带来源时间与不确定性
- **B09-02-A3** 用户撤销后停止监听与后续转发

**验证层/目录：** L5-L6 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 撤销通知授权/测试通道，只按用户指定清理测试缓存。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B09-03 · 手机与Agent待办合并呈现

**前置：** B09-02, B08-01；**需求：** R036, R038, R039

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: examples/integrations/device-inbox/aggregator/`

### 实施
1. 聚合只保存可重建投影，标明原文/摘要/推断
2. 分开需要回复、需要决策、普通通知，不依标题相似合并
3. 返回来源/复制草稿先行，发送消息另行授权

### 验收
- **B09-03-A1** 能够显示用户场景：若干Agent等待与一条联系人待回复，并注明模拟/真实
- **B09-03-A2** 去重以来源身份而非文本近似
- **B09-03-A3** 通知正文中的指令不能授予执行权限

**验证层/目录：** L1-L6 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 拆回独立来源卡片，保留各权威系统状态。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B09-04 · 多通道故障与隐私验收

**前置：** B09-03；**需求：** R037, R038, R039, R070

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: tests/device-inbox/`；`docs/remote.md`

### 实施
1. 用外部transport替身测试断连、延迟、重复、换路，不实现网络路由
2. 检查端到端身份与消息重放
3. 对真实单通道跑退出/休眠/重连；其他链路NOT_RUN

### 验收
- **B09-04-A1** 不宣称BLE/USB/热点全部贯通
- **B09-04-A2** relay可能读内容时明确说明，不能冒充端到端加密
- **B09-04-A3** 日志无真实消息正文和凭据

**验证层/目录：** L1-L6 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 断开本批测试桥接，恢复只读本地面板。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B10-01 · PCSense孵化窄原型

**前置：** B06-04, B07-04；**需求：** R017, R050, R068

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: examples/incubation/pcsense/`

### 实施
1. 只选一个已有来源可支撑的设备/任务工作流
2. 以配置+Provider构建不改Host业务分支
3. 记录缺失原语、用户价值与迁出边界

### 验收
- **B10-01-A1** 原型可用且没有ERP业务进入Core
- **B10-01-A2** 来源替换不要求Host专用补丁
- **B10-01-A3** 未经证据不宣称独立APP等价完成

**验证层/目录：** L2-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 卸载本配置/Provider即可退出，不移走用户业务数据。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B10-02 · 毕业与可移植性演练

**前置：** B10-01；**需求：** R017, R068, R072

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `proposed: docs/incubation/graduation.md`；`proposed: examples/incubation/`

### 实施
1. 将业务模型从界面声明分离，导出无秘密配置
2. 演示由另一壳调用同一Provider或独立UI端口
3. 记录仍依赖WinCraft的能力和迁移成本

### 验收
- **B10-02-A1** 毕业无需复制WinCraft内核或剥离业务数据库
- **B10-02-A2** 既有许可与来源边界不被擅改
- **B10-02-A3** 用户可停止使用Host而不失去业务记录

**验证层/目录：** L0-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 保留原Provider入口，实验壳可删除。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B10-03 · 窗口组与角色可能性最小POC

**前置：** B04-02, B06-03；**需求：** R034, R056, R057, R058

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `apps/desktop/src-tauri/src/windows.rs`；`proposed: docs/poc/presentation-extensions.md`

### 实施
1. 分别选择临时窗口组和受控素材状态映射做小型POC
2. 窗口组逐成员检查租约与回执，角色无业务情绪引擎
3. AppBar/DWM/区域输入/捕获每项独立记录，不一次全开放

### 验收
- **B10-03-A1** 部分OS操作失败可观察，不假装全组原子
- **B10-03-A2** 减少动画/关闭/救援可用
- **B10-03-A3** 任何捕获排除仅用户启用且不承诺保密

**验证层/目录：** L1-L4 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 撤销行为/关闭POC能力，恢复独立普通窗口。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B10-04 · 独立创作者验证与外部参考更新

**前置：** B10-01, B06-04, B02-03；**需求：** R033, R050, R059

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `docs/`；`skills/wincraft-provider/`；`proposed: docs/research/creator-validation.md`

### 实施
1. 邀请未参与内核的作者仅用公开文档完成一个Provider/配方
2. 记录首次可用路径、失败点与需改核心的次数
3. 修复真实文档/API摩擦，不以搭官网替代创作验证

### 验收
- **B10-04-A1** 来源、构建、连接、错误恢复均可由外部作者复现
- **B10-04-A2** 同一组件/配方被第二个场景复用
- **B10-04-A3** 指标如实记录，不虚构社区用户或需求规模

**验证层/目录：** L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 撤回无证据宣传，只保留真实反馈与兼容修复。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B11-01 · 持续兼容与资源性能基线

**前置：** B03-04, B02-04；**需求：** R060, R061, R062

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `tests/`；`.github/workflows/verify.yml`；`docs/performance.md`

### 实施
1. 针对本次拟发布的已实现能力建立旧Provider/协议fixture矩阵；未实现路线不成为首发前置
2. 采全进程树/句柄/内存/CPU/尾延迟/创建销毁测量
3. 长运行/睡眠/来源崩溃后资源回收，阈值由实测ADR确定

### 验收
- **B11-01-A1** 每次测量带机器/版本/负载而非泛称轻量
- **B11-01-A2** 无资源持续泄漏趋势或明确阻塞发布
- **B11-01-A3** 未测性能不写宣传数字

**验证层/目录：** L1-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 回退导致回归的单批改动，不修改历史基线。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B11-02 · Windows发布前原生验收

**前置：** B11-01, B02-04；**需求：** R047, R055, R057, R061

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `apps/desktop/src-tauri/`；`docs/windows.md`；`docs/engineering/VALIDATION.md`

### 实施
1. 干净环境独立release，不依赖Vite/开发工具
2. 多屏DPI、IME、焦点拒绝、托盘/穿透救援与更新回退
3. 记录签名/安装/权限提示/用户可卸载状态

### 验收
- **B11-02-A1** 发布声明只含实测能力
- **B11-02-A2** 隐藏不销毁与原生minimize语义没有混淆
- **B11-02-A3** 取消/退出后无残留hotkey/窗口/授权资源

**验证层/目录：** L4-L5 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 回退上个已验收版本，保留用户配置可导出。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B11-03 · macOS/Linux能力矩阵与受限试构建

**前置：** B01-01, B11-01；**需求：** R002, R046

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `apps/desktop/src-tauri/`；`proposed: docs/platforms/`

### 实施
1. 分别列macOS/X11/Wayland原生能力、权限和限制
2. 复用核心与协议，只替换必要native adapter
3. 有环境才构建验收，无环境保持NOT_RUN，unsupported可降级

### 验收
- **B11-03-A1** Tauri编译成功不等于原生交互等价
- **B11-03-A2** 跨平台Capability如实报告
- **B11-03-A3** 不会为迁移破坏Windows现有契约

**验证层/目录：** L6 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 保留Windows已验收实现，新平台特性关掉。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果

## B11-04 · 集体治理与公众发布准备

**前置：** B11-02, B00-02；**需求：** R030, R033, R043, R044, R047, R049, R070

**输入：** 当前工作区、相关owner_doc、现有测试和对应source_ids；只使用合成或明确授权数据。

**定位：** `README.md`；`LICENSE-NOTES.md`；`proposed: docs/release/`；`proposed: CONTRIBUTING.md`

### 实施
1. 维护者角色作为提案，未经同意不改仓库权限
2. 保留许可与署名，准备中英发布范围/已知限制/来源说明
3. 审阅私有引用、凭据、签名、依赖与实际发布授权

### 验收
- **B11-04-A1** 无擅自重许可/定名/归属迁移
- **B11-04-A2** 未获发布授权仅生成材料不发Release
- **B11-04-A3** 公众文档可读且适用版本/更新时间明确

**验证层/目录：** L0-L6 / current WinCraft checkout

```text
npm run check
python scripts/check_contracts.py
cargo test --workspace
```

**说明：** 先补本任务精确正反测试；以下是当前已知基线命令，不替代任务专用用例；原生声明须另跑npm run desktop:build及独立release；外部来源无授权标BLOCKED

**回滚：** 撤回未发布材料，已授权发布回退须按正式发布流程。

**证据：** baseline commit及工作区差异、实际命令/退出码与环境、用例状态和不含秘密的证据路径、未测项/阻塞来源、回滚验证结果
