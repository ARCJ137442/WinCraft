---
title: WinCraft 0.1.0-alpha.1 Windows 验收指南
updated_at: 2026-10-31
last_verified_at: 2026-10-31
status: local-release-acceptance-guide
audience: maintainer, Windows tester
---

# WinCraft 0.1.0-alpha.1 Windows 验收指南

## 本次构建

| 项目 | 值 |
|---|---|
| Tauri Host EXE 源码提交 | `a78b3c9d4e9e19be7045faad4920d060f3c990c1` |
| Agent Activity Provider 示例 | `0696cbeb9b3ef69cb9c6a9b43901fae6e922ea7b`（仓库内 Python 示例，单独运行，不打包进 EXE）|
| 程序路径 | `target/release/wincraft-desktop.exe` |
| 文件大小 | 13,595,648 bytes |
| SHA-256 | `64458EA768A36FE012230EA34D0E37936FB1ACF1FA74C1A49802C8D456BD7314` |
| 产品文件版本 | `0.1.0-alpha.1` |

这是单个 Windows 可执行文件，不是安装器。Tauri Host EXE 来自源码提交 `a78b3c9`；最新本地工作树 `npm run check:local` 退出码 0：28 项 UI、145 项 Rust、205 项 Python（1 项 Windows symlink 用例因环境能力跳过）、离线契约、Clippy 和 Provider Skill 检查通过。`npm run desktop:build` 退出码 0，产物信息见上表。GitHub Actions run [41123291608](https://github.com/exomind-team/WinCraft/actions/runs/41123291608) 已通过，Windows source job 用时 9m59s。Agent Activity Python Provider 的此前跨来源详情保留修复位于仓库提交 `0696cbe`，其 `npm run check:local` 在 Windows Actions run [41128511607](https://github.com/exomind-team/WinCraft/actions/runs/41128511607) 通过（12m58s）；当前未打包进 EXE 的 Python 示例又新增 Codex App 详情跨来源恢复回归，完整本地总门禁结果见验证矩阵。自动测试和 CI 不替代原生 GUI 验收。

首次 release 曾因在同步 Tauri setup 回调直接调用 `tokio::spawn` 而以 101 退出；现已改为通过 `tauri::async_runtime::spawn` 调度并通过完整本地门禁。当前 `a78b3c9` release EXE 构建完成，但本轮未启动该 Tauri EXE 做像素/托盘验收；临时 scope 生命周期验证使用真实 headless Rust Host。以下空白人工验收项仍需由维护者实测。

2026-10-30 用户明确要求改用本机进程状态与磁盘会话数据，不需要与 Codex App 通信。当前源码包含 Codex App state DB/rollout 与 Claude Code JSONL/subagent 只读适配；count-only smoke 确认 Codex App 进程在线、Claude Code 进程离线但历史可读。标准 release 上的只读 live provider 以 `codex`、`codex-app`、`claude-code` 三源运行，真实提交了三次场景快照并清理自己的临时世界；来源摘要为 Codex CLI online/0、Codex App online/128、Claude Code offline/128。它证明三源进入同一个 Host scene 更新路径，不证明像素呈现：本机没有取得 Agent Activity 截图或 accessibility tree，所以标题/项目/Agent 输出卡片、freshness 展示和 UUID-only 深链接仍为 `NOT_RUN`。

## 快速启动

1. 如果已有 WinCraft 实例，先从它的托盘菜单选择“退出”，再打开 `target/release/wincraft-desktop.exe`。普通启动预期只有托盘图标，不自动打开业务窗口。
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
| 本机全局快捷键（B04-03） | 默认未注册；管理器中明确启用后按下组合键应打开/聚焦管理器；停用后按键不再触发。注册冲突和 IME/系统保留组合必须失败关闭。 | Rust 回归和 release build：PASS；当前构建的真实启用/按键/冲突/撤销/IME：NOT_RUN |
| Agent Activity 会话卡片（B08-02/B08-03） | Codex App/CLI/Claude 来源卡片显示名称、状态、项目和来源文本；无权威逐会话状态时显示未知。 | 16 项总览测试覆盖来源切换时恢复 Codex App/CLI/Claude 各自详情 identity/page、missing tombstone 保留 freshness 与撤销 unknown；三源 live Host scene 和 scope lifecycle L4 smoke 通过。当前 release 像素仍 NOT_RUN；scope 撤销不能映射为外部会话撤销，B08-03-A4 仍 PARTIAL。|
| 置顶与透明度（W12） | 默认置顶且默认透明度 80%；普通窗口不能覆盖；另一个置顶窗口遵循 Windows z-order；provider 配置后实际效果可见。 | ____ |
| 点击穿透救援（W09） | 启用穿透后仍能从托盘/管理器救援；窗口恢复可点击、可见、在屏幕内；旧写者失权。 | ____ |
| 多屏与缩放（W11/W28） | 在不同 DPI、负坐标副屏和显示器拔插后检查位置/尺寸，窗口仍可找回。 | ____ |
| Windows 虚拟桌面 | “显示在所有桌面”当前尚未实现；记录为 `NOT_IMPLEMENTED`，不能把无效果的开关算作通过。 | NOT_IMPLEMENTED |

完整分层用例见 [`docs/engineering/ACCEPTANCE.md`](../engineering/ACCEPTANCE.md)。当前本地真实 Rust Host lifecycle smoke（`scoped_live_sources.py --duration-seconds 5`）退出码 0：两个独立 Provider scope 从 `online → stale`，父 authority 删除 Codex scope 后 Codex 为 `revoked`、Claude Code sibling 仍为 `stale`；临时世界清理成功。该 smoke 使用 headless Rust Host，验证协议与来源进程隔离，不证明 Tauri 像素、托盘点击、真实 z-order、穿透救援或多显示器行为。会话记录丢失仍显示撤销未知；scope 撤销状态不能替代来源会话状态。

## 记录与复现

本次构建命令为 `npm run desktop:build`，产物位于 Cargo target release 目录。工具版本、退出码和脱敏探针摘要保存在默认忽略的 `evidence/local/nextgen-2026-10-31/scope-status-lifecycle-smoke.json`。不要把 `.runtime.json`、令牌、Obsidian 笔记或 TrafficMonitor 遥测写入提交。

## B06-03 配置包导入人工验收

此前 release 的管理器 accessibility tree 已读取；当前 `a78b3c9` release 尚未启动，B06-03 的预览、授权重规划、应用、Provider 回执和回退操作仍未逐项实测。以下步骤可由维护者在“窗构 · 世界管理器”中完成。数据全部为合成样例；不使用真实 Provider 或用户世界。

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
