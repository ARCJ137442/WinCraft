---
title: WinCraft 0.1.0-alpha.1 Windows 验收指南
updated_at: 2026-10-30
last_verified_at: 2026-10-30
status: local-release-acceptance-guide
audience: maintainer, Windows tester
---

# WinCraft 0.1.0-alpha.1 Windows 验收指南

## 本次构建

| 项目 | 值 |
|---|---|
| 源码提交 | `309af176714ffaf4d76601124a32e43ab2dfdd0b` |
| 程序路径 | `target/stage-309af17/release/wincraft-desktop.exe` |
| 文件大小 | 13,559,808 bytes |
| SHA-256 | `6840654D6DBEFB780B758618805B241AC96D22D57B8E7F4D49B102DFA3E58E10` |
| 产品文件版本 | `0.1.0-alpha.1` |

这是单个 Windows 可执行文件，不是安装器。`npm run check:local` 退出码 0：28 项 UI、141 项 Rust、174 项 Python（1 项 Windows symlink 用例因环境能力跳过）、离线契约、Clippy 和 27 个 Provider Skill 引用检查通过；Windows Actions run [41024348330](https://github.com/exomind-team/WinCraft/actions/runs/41024348330) 对 `309af17` 也通过。设置隔离 `CARGO_TARGET_DIR=target/stage-309af17` 后，`npm run desktop:build` 退出码 0。该新 EXE 尚未另行启动：之前的 4bc3e81 候选仍开着世界管理器窗口，避免重复创建托盘宿主。CI 与自动测试不替代原生 GUI 验收。

首次 release 启动时，管理器后台循环在同步 Tauri setup 回调直接调用 `tokio::spawn`，进程以 101 退出；已修复为通过 `tauri::async_runtime::spawn` 调度，并重新构建验证。Computer Use 随后被物理 Escape 停止：未输入或启用快捷键，也未完成托盘交互。本指南中的空白验收格仍须由维护者实际操作填写。

2026-10-30 用户明确要求改用本机进程状态与磁盘会话数据，不需要实时 Codex App connector。当前源码包含 Codex App state DB/rollout 与 Claude Code JSONL/subagent 只读适配；本机 count-only smoke 确认 Codex App 进程在线、Claude Code 进程离线但历史可读。最新 release 的管理器窗口和 accessibility tree 已观察；本次没有打开 Agent Activity 世界，因此真实会话卡片、像素截图、UUID-only 深链接仍为 `NOT_RUN`。不把 synthetic UIA 或协议 smoke 计作真实 UI 接入。

## 快速启动

1. 先从此前已运行的 WinCraft 实例托盘菜单选择“退出”，再打开 `target/stage-309af17/release/wincraft-desktop.exe`。普通启动预期只有托盘图标，不自动打开业务窗口。
2. 从 WinCraft 托盘菜单打开“世界管理器”。多次点击应聚焦同一个管理器实例。
3. 在管理器中新建空白世界；需要自动打开管理器时，可使用可选参数 `--open-manager`。这个参数是本机联调用入口，不代表默认启动行为。
4. 从管理器复制它显示的 runtime descriptor 路径给本机 Python 示例，例如：

   ```powershell
   python examples/python/focus_demo.py --runtime "<管理器显示的 runtime descriptor 路径>"
   ```

   descriptor 只在本机使用，不要复制到聊天、截图或提交记录。

5. 完成后从托盘选择“退出”。检查本次宿主进程退出、本次 descriptor 清理；不要结束其他应用的 WebView2 进程，也不要批量删除旧 runtime 文件。

## 人工验收清单

每项填写 `PASS`、`FAIL`、`BLOCKED` 或 `NOT_RUN`。失败时记录步骤、现象、Windows 缩放比例/显示器数，并附遮蔽本机路径和用户内容的截图。

| 检查 | 预期结果 | 结果 |
|---|---|---|
| 托盘启动与退出（W01） | 默认仅托盘；托盘打开管理器；最后关闭业务窗口后宿主仍运行；托盘“退出”正常结束宿主并清理本次 descriptor。 | ____ |
| 管理器复用（W02/W13） | 再次打开聚焦同一个管理器；隐藏的管理器可重新呈现；关闭普通世界与管理器遵循各自语义。 | ____ |
| 动态组件与动作回执（W04/W05/W06） | 在 Python focus demo 中点击“替换组件区”和一个按钮；结构实时更新，动作显示当前 provider 的实际回执；provider 断线不冒充成功。 | ____ |
| 自动尺寸与文本（W07/W15） | 调宽/调窄 Obsidian Workspace 或 TrafficMonitor；高度随内容布局收敛；长中文/长无空格文本在组件内换行；底部和右侧默认无窗口级滚动条。 | ____ |
| 折叠、拖动、隐藏（W18/W20） | 折叠后窗口只剩标题栏且宽度收紧；展开恢复；标题栏隐藏时普通背景仍可拖动；隐藏后可从管理器恢复同一 world。 | ____ |
| 本机全局快捷键（B04-03） | 默认未注册；管理器中明确启用后按下组合键应打开/聚焦管理器；停用后按键不再触发。注册冲突和 IME/系统保留组合必须失败关闭。 | Core/server 回归与 release build：PASS；本机真实按键与撤销：NOT_RUN |
| Agent Activity 会话卡片（B08-02/B08-03） | Codex App/CLI/Claude 来源卡片显示名称、状态、项目和来源文本；Codex App 输出须经 UUID 与 `session_meta` 匹配，Claude 输出只来自 assistant 文本。进程状态与磁盘读取质量分开；没有权威逐会话状态时显示未知。 | 工作树定向测试与本机 count-only 进程/磁盘 smoke：PASS；Codex App 当前 release UI 与 UUID 深链：用户要求阶段性标记停滞（NOT_RUN） |
| 置顶与透明度（W12） | 默认置顶且默认透明度 80%；普通窗口不能覆盖；另一个置顶窗口遵循 Windows z-order；provider 配置后实际效果可见。 | ____ |
| 点击穿透救援（W09） | 启用穿透后仍能从托盘/管理器救援；窗口恢复可点击、可见、在屏幕内；旧写者失权。 | ____ |
| 多屏与缩放（W11/W28） | 在不同 DPI、负坐标副屏和显示器拔插后检查位置/尺寸，窗口仍可找回。 | ____ |
| Windows 虚拟桌面 | “显示在所有桌面”当前尚未实现；记录为 `NOT_IMPLEMENTED`，不能把无效果的开关算作通过。 | NOT_IMPLEMENTED |

完整分层用例见 [`docs/engineering/ACCEPTANCE.md`](../engineering/ACCEPTANCE.md)。本次构建的真实 Tauri-hosted `lease_probe.py` 返回 `PASS`、退出码 0；B07-02 scope probe 也通过。这些协议探针不替代托盘点击、像素布局、真实 z-order、穿透救援及多显示器人工操作。当前 provider 从进程读取 Codex App/Claude 在线状态，从本机数据目录读取会话摘要；无进程仍显示可读历史，数据缺失明确显示未知/不可用。Computer Use 曾观察到管理器截图，但未保存，因为画面含本机 runtime 路径；真实 Codex App 卡片和深链接仍未验收。

## 记录与复现

本次构建命令为 `npm run desktop:build`，产物位于 Cargo target release 目录。逐命令退出码、工具版本和脱敏探针结果保存在默认忽略的 `evidence/local/nextgen-2026-10-30/`。不要把 `.runtime.json`、令牌、Obsidian 笔记或 TrafficMonitor 遥测写入提交。

## B06-03 配置包导入人工验收

当前 release 的管理器 accessibility tree 已读取，但 B06-03 的预览、授权重规划、应用、Provider 回执和回退操作尚未逐项实测；以下步骤可由维护者在“窗构 · 世界管理器”中完成。数据全部为合成样例；不使用真实 Provider 或用户世界。

### 样例与提供者

- 预生成 `.wcp`：`evidence/local/nextgen-2026-10-30/workday-synthetic.wcp`，1,109 bytes，SHA-256 `3407EC6895809A6227860E6E83E952DCC3DF31B083123C5E8FD6171E8527A840`。它只含 `pack.json` 与声明的 blueprint；需要时从仓库根目录重建：

  ```powershell
  python tools/pack/export_pack.py --pack docs/strategy/2026-10-26/examples/packs/workday.pack.json --output evidence/local/nextgen-2026-10-30/workday-synthetic-rebuild.wcp
  ```

  exporter 不覆盖已存在的输出；重建后使用命令生成的新文件路径。

- 在另一个 PowerShell 窗口启动合成 Provider，`<runtime descriptor>` 使用管理器当前显示的本机路径，不复制文件内容或令牌：

  ```powershell
  python examples/python/pack_provider_demo.py --runtime "<runtime descriptor 路径>" --duration-seconds 30
  ```

  Provider 只注册 `agent-board` 的合成 inventory，声明 `activity.read` 与 `world.import.accept`，等待本机确认后才接入新世界。

### 流程与预期

| 步骤 | 操作 | 预期 |
|---|---|---|
| 1. 预览 | 在管理器“配置包路径”中填入上述 `.wcp` 路径，点“预览配置包”。 | 显示来源与权限需求；`activity.read` 未批准时计划受阻。已有世界不变。 |
| 2. 撤销预览 | 点“取消”，再刷新或重新打开管理器检查。 | 提示“预览已取消；现有世界未更改。”没有新增窗口。 |
| 3. 授权并重规划 | 再预览，选择 `Synthetic pack provider`，只批准本样例请求的 `activity.read`；按提示重新预览。 | 授权会改变清单 generation，旧预览失效；新预览显示可选 `metrics` 来源缺失及 fallback，状态为“可选来源缺失”。 |
| 4. 明确应用 | 点“确认并创建窗口”。 | 只创建 blueprint 声明的新窗口；原有世界不替换。合成 Provider 收到定向 `world.import.joined`，窗口从静态内容更新到合成进度条，然后 Provider 正常离开并保留窗口。 |
| 5. 回退确认 | 在导入记录中点“查看回退选项”，检查说明，再点“确认回退”。 | Provider 已更新并加入的 Agent 窗口应保留；未被后续改变的可选指标 fallback 窗口可清理，结果应说明部分回退。不得删除其他/已编辑世界。 |
| 6. 新鲜度栅栏（可选） | Provider 运行期间先预览，等待它下一轮 inventory generation 更新，再尝试应用旧预览。 | 旧预览被拒绝并要求重新预览；不会创建窗口。 |

逐项把结果写入 [`docs/strategy/2026-10-26/plan/acceptance.json`](../strategy/2026-10-26/plan/acceptance.json) 的 B06-03-A1/A2/A3，并附上脱敏截图。不要截图 runtime descriptor 或复制令牌；完成后退出合成 Provider 与本次 WinCraft 宿主。直到这些 UI 项通过，本任务继续保持 `IMPLEMENTED_UNVERIFIED`/`PARTIAL`。

## B06-04 配置包跨环境分享验收

此项需要两个彼此独立的 Windows 用户环境或设备；同一 Host 下开两个窗口不算。将上一节生成的 `workday-synthetic.wcp` 复制过去即可，**不要复制 runtime descriptor、授权记录或 Provider 状态**。

1. 在第二环境打开 WinCraft；没有注册来源时，先预览包。必选 `agents` 来源应显示受阻，管理器不得自动下载、安装或运行 adapter/Provider；可选 `metrics` 缺失应给出降级/替代说明。
2. 在该环境单独选择/启动一个受信任的合成 Provider，并使用该环境自己的 runtime descriptor。仅在预览明确列出 `activity.read` 后才由本机用户批准；然后重新预览并再次确认应用。
3. 在第一环境重复同一 `.wcp` 流程。两个环境的 provider instance、grant、world ID 和 import ledger 应独立；pack 本身不携带这些身份或授权。
4. 检查分享文件只含 `pack.json` 与声明的 blueprint，不含原机绝对路径、token、runtime descriptor 或私有标题。将两个环境各自的结果记录在 B06-04-A1/A2/A3；单机 fixture 和 exporter 测试不能替代此验收。

截至本指南更新时间，跨两个用户环境的导入与重新授权尚未执行，B06-04 仍为 `IMPLEMENTED_UNVERIFIED`/`PARTIAL`。
