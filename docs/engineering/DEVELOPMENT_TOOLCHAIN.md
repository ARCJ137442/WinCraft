# 开发规范与工具链

## 目标

让 WinCraft 的一次功能改动从可观察的用户行为开始，并能用合适层级的证据复验。工具链提供一致入口；它不把静态检查、模拟数据或构建成功冒充成真实宿主与用户验收。

## 开发约定

1. 先写一个 Given / When / Then 场景，描述使用者可观察到的行为；再为该行为补或复用回归测试。
2. 测试公共行为和协议承诺，不把内部函数布局当作测试契约。检查可能的反例、断线、旧租约、部分失败和恢复路径，只在该功能确实涉及这些风险时加入。
3. 先跑受影响的最小层级，再跑统一本地检查。UI/离线契约、Rust workspace、Python provider 和真实宿主/原生 UI 是不同证据，分别记录。
4. 每条验证结论绑定仓库版本、工作树是否有未提交改动、运行环境、实际命令和退出码；涉及可执行产物时记录真实路径与哈希。缺少证据写 `NOT_RUN`、`BLOCKED` 或 `UNKNOWN`，不推定通过。
5. 以当前用户要完成的一项工作检验改动是否有用。提案、提交量、测试数量和工具本身不等于用户收益；若假设被反例推翻，应缩小、改动或停止。
6. 接收私有研究包时只提炼经 WinCraft 需求核对后可用的通用原则；不把原始私有材料、个人路径、评测答案、凭据或用户业务内容复制到公开仓库。

这些约定吸收了本项目过往验证经验及 TouchAI 工具链中的行为优先与统一检查入口。它们是 WinCraft 项目规范，不要求引入 TouchAI 的语言栈、依赖或仓库治理流程。

## 从需求到复用

产品判断和工程交付是两条反馈循环，在一个可观察的用户承诺处会合：

```text
用户正在做什么、现在怎样完成
              ↓
一个能被反例推翻的行为承诺
              ↓
最小且可回退的实现 + 对应层级的证据
              ↓
实际试用 → 收益/失败反馈 → 继续、修订或停止
              ↓
后续真实任务再次采用
```

新工具、统一数据结构或大计划不是启动真实任务的前置条件。先使用仓库已有的 Issue、验收矩阵、验证记录和测试；只有真实变化无法清楚表达或复验时才补充工具。记录反例和停止条件，避免只收集支持原方案的材料。

将“已表达、已实现、已试用、观察到收益、重复采用”作为描述成熟度的词汇，不折算成总分。比如编译通过只证明它编译；一次通过的测试不能自动证明用户收益；某个任务当前未使用也不能单凭提交间隔推断原因。

## Provider 教程与 Agent 指引

`skills/wincraft-provider/scripts/verify.py` 检查教程需要的仓库文件与引用存在。它不是 Agent 行为评测，也不证明新提供者已能连接真实宿主。组件 schema/fixture 测试检查的是输入输出契约；真实提供者联调仍须记录宿主版本、运行路径、动作回执与失败边界。评审 Skill 或教程时使用与本次目标相符的行为场景，不把静态结构检查的 PASS 升格为熟练接入能力。

## 环境与安装

- Windows：Rust stable、Node.js 22、Python 3.11+；构建 Tauri 另需 Windows C++ Build Tools 与 WebView2 Runtime。
- Node 依赖由根目录 `package-lock.json` 固定。新 checkout 使用 `npm ci`，不要用 `npm install` 改写 lockfile，除非确实调整依赖。
- Python 开发依赖：

  ```powershell
  python -m pip install -r requirements-dev.txt -r examples/python/requirements.txt
  ```

- Rust workspace 依赖由 `Cargo.lock` 固定；使用 `cargo` 原生解析，不手工编写锁文件。

## 统一本地验证

完整静态和自动化回归入口：

```powershell
npm run check:local
```

它依次运行：

| 命令 | 覆盖 |
|---|---|
| `npm run check` | UI 构建与 Node 行为测试、离线 schema/配置检查 |
| `npm run check:rust` | workspace rustfmt 检查、所有 target 的 Cargo check、workspace 测试、严格 Clippy |
| `npm run check:python` | Python provider 单测与提供者 Skill 文件/引用验证 |

常见分层命令：`npm run test:ui`、`npm run check:contracts`、`cargo test --workspace --no-fail-fast`、`python -m unittest discover -s tests -v`。修复 rustfmt 问题时运行 `cargo fmt --all`，审阅差异后再运行统一检查。

`npm run desktop:dev` 用于开发；`npm run desktop:build` 产出独立 release。CI 与本地检查通过，只能证明它们实际覆盖的代码和行为；不能证明托盘、窗口位置、拖动、点击穿透、多显示器或人工交互通过。Native/manual 验收仍按 [`ACCEPTANCE.md`](ACCEPTANCE.md) 记录。

## CodeGraph

CodeGraph 是每个工作树的本地导航索引，不是源码真相，也不是构建前置条件。已在本机用 CodeGraph CLI 1.5.0 建立 WinCraft 索引；其生成数据库保存在被忽略的 `.codegraph/`。

```powershell
npm run codegraph:init    # 当前 checkout 尚无索引时执行一次
npm run codegraph:explore -- "window drag and geometry control"
npm run codegraph:sync    # 源码变更后同步索引
npm run codegraph:status  # 检查索引是否新鲜
```

新机器需要先安装并确认 `codegraph --version` 可用。索引只辅助定位符号与调用关系；未命中、结果过期或关系不确定时回到 `rg` 和源码。不要提交、压缩分享或写入证据包中的 `.codegraph` 数据库。

## CI 边界

`.github/workflows/verify.yml` 在 `dev` 的 push、面向 `dev` 的 pull request 和手动触发时执行 `npm run check:local`。CI 使用 Windows runner，以覆盖当前 Tauri 目标的 Rust 编译边界。`.github/pull_request_template.md` 要求变更说明行为场景，并区分自动检查、真实宿主与人工验收。CI 不自动启动真实交互窗口，也不替代 `docs/engineering/ACCEPTANCE.md` 中需要 UIA、Computer Use 或人工操作的用例。

## 证据成熟度

讨论功能从愿望到日用时，可以按下面的顺序描述现状，而不把它做成分数或发布门槛：

| 阶段 | 含义 |
|---|---|
| 已表达 | 有清楚的用户目标或行为承诺 |
| 已实现 | 有可审阅的代码或配置 |
| 已试用 | 在明确版本、环境和场景下实际运行 |
| 已观察收益 | 使用者或任务结果显示问题有所改善 |
| 已重复采用 | 在后续真实工作中再次使用 |

状态可以因新反例而退回。`npm test`、截图或 Agent 自述分别只支持它们实际观察到的范围，不单独证明日用收益。
