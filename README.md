# WinCraft · 可组合桌面窗口运行时

**版本：0.1.0-alpha.1 / 原型源码交接，非已验收发行版。**

本机 lifecycle release 已与真实 TrafficMonitor x64 provider、Obsidian Obsidian Workspace 只读 provider 联调；可提交的验证摘要见 [`docs/engineering/VALIDATION.md`](docs/engineering/VALIDATION.md)，逐项本机记录位于默认不提交的 `evidence/local/`。TrafficMonitor 桥接已从当前源码重编并实测报告 1.8.6.0；这仍是本地原型验证，不代表对外发行或安全认证。

让已有应用、自动化脚本与 Agent 通过声明式协议，获得可搭建、可交互、可操控的桌面窗口。世界就是窗口；宿主是托盘进程；提供者是加入世界的参与者；组件是可以持续增删重组的方块。

> **先读 [START_HERE.md](START_HERE.md) 和 [CODEX_HANDOFF.md](CODEX_HANDOFF.md)。**
> 制作环境事实与后续本机摘要见 [验证记录](docs/engineering/VALIDATION.md)；机器专属的细化命令日志放在默认忽略的 `evidence/local/`。功能列表表示源码覆盖范围，不代表每项验收均通过。

## 产品边界

业务状态由提供者裁决；宿主保存可重建的界面、连接和借用状态。调用方不提交 HTML/JavaScript，不需要前端工具链。宿主只承载自己的可信渲染器，不使用 Electron。

首版使用 **Rust 核心 + Axum/WebSocket 协议 + Tauri 2 原生窗口适配 + 无运行时框架依赖的 TypeScript 组件渲染器**。浏览器预览不是运行时；Node.js 只用于开发构建，生产运行不需要 Node 伴随进程。

“WinCraft”为内部工作名，“窗构”为临时中文显示名，均不代表本轮完成正式品牌定名或查重授权。

## 已写入源码的首版能力

| 层 | 原型实现 |
|---|---|
| 核心 | 创建/列出/加入/离开/销毁世界；窗口级独占写租约；多个快照读者；租约续期、过期、撤销编号；版本冲突检查 |
| 声明式界面 | 10 种组件；JSON Pointer 数据绑定；运行中插入、删除、替换、移动和改属性；整批事务验证 |
| 窗口 | 位置、尺寸、默认置顶（可配置）、显隐、装饰、任务栏、调整大小、点击穿透、人类/提供者几何控制；透明度默认 80%，文本默认可选，标题栏文字不可选；屏幕内恢复 |
| 交互 | 组件动作回到当前写入者；等待/确认/失败/超时；拒绝过时界面的动作 |
| 自用管理器 | 宿主内部提供者生成的管理与设置世界；共享同一组件树和渲染器；明确的本地接管/解除接管/关闭 |
| 网络 | 统一健康检查与鉴权发现、协议握手、双向 WebSocket；非本机提供者可通过 SSH 隧道接入 |
| 开发支撑 | 可独立运行的 headless Rust 宿主；Python 示例、真实协议验收探针、只读外心桥接；Windows 自动化验证 CI |

上述是**源码覆盖范围**，不是全部运行验收通过的功能清单。尤其 Tauri/Win32、WS 端到端与外心实机链路必须由本地 Codex 验证。

## 快速开始

准备 Rust stable、Node.js 22、Python 3.11+；Windows 桌面构建另需微软 C++ 构建工具与 WebView2。先依据 Tauri 官方 prerequisites 完成机器环境。

```powershell
npm ci
python -m pip install -r requirements-dev.txt -r examples/python/requirements.txt
npm run check:local
npm run desktop:dev
```

本地开发规范、CodeGraph 索引和分层验证边界见 [`docs/engineering/DEVELOPMENT_TOOLCHAIN.md`](docs/engineering/DEVELOPMENT_TOOLCHAIN.md)。

桌面启动后默认只有托盘，不自动弹出主界面。从托盘打开“世界管理器”，获取连接描述文件的路径。

本机自动化也可显式打开管理器窗口；不带该参数仍保持托盘优先：

```powershell
npm run desktop:build
Start-Process -FilePath '.\target\release\wincraft-desktop.exe' -ArgumentList '--open-manager' -WindowStyle Hidden
```

```powershell
python -m pip install -r examples/python/requirements.txt
python examples/python/focus_demo.py --runtime "<管理器显示的实际 .runtime.json 路径>"
```

只测试真实 Rust 核心和网络、不启动原生窗口：

```powershell
cargo run -p wincraft-server --bin wincraft-headless
python examples/python/lease_probe.py --runtime "<终端输出的实际 .runtime.json 路径>"
```

不要猜默认端口；宿主默认随机选择空闲端口。连接描述文件包含令牌，不应发到聊天、提交 Git 或公开分享。

## Agent 提供者教程

为 WinCraft 接入自动化程序或 Agent，从 [`skills/wincraft-provider/SKILL.md`](skills/wincraft-provider/SKILL.md) 开始。教程按“加入世界 → 搭建声明式场景 → 动态更新 → 回执动作 → 租约恢复”逐步讲解，并链接到真实 Python 示例。
TrafficMonitor 的本机插件桥接、隔离 staging 与运行步骤见 [提供者参考](skills/wincraft-provider/references/trafficmonitor.md)。
Obsidian Obsidian Workspace 仪表盘只读投影见 [Obsidian 集成指南](docs/integration-obsidian.md)。

只读 Agent Activity 总览示例见 [`examples/integrations/agent-board/README.md`](examples/integrations/agent-board/README.md)。它把 Claude Code 后台 Agent、Codex CLI 本机状态库和 Codex App 来源分开采集；来源页统一显示会话名称、状态、项目和可用文本。Codex App 可由授权 Agent connector 提供快照，也可从只读本机状态库有限补充 `Codex Desktop` 会话标题/项目；本机状态不能证明运行状态，最近 Agent 输出只从 UUID 匹配的有限 rollout 尾部提取。单纯打开 Codex App 不会建立实时 connector 桥接。Codex CLI preview 不标注发言方；Claude `agents --json` 没有最近输出字段。该示例不读取完整会话日志，也不提供批准、写文件或继续执行动作。

## 单独看前端

```powershell
npm run ui:dev
```

访问本机 `http://127.0.0.1:1420/`；管理器演示为 `?preview=manager`。页面明确标识模拟数据，不能用截图证明原生窗口、Rust 所有权或真实业务链路通过。

## 目录

```text
crates/wincraft-core/       世界、租约、组件、事务、版本与状态机
crates/wincraft-server/     真实 Rust 协议服务、内部管理提供者、headless 入口
apps/desktop/src-tauri/     托盘、原生窗口、受限 IPC、窗口监督与诊断
apps/desktop/src/           共享组件渲染器与显式浏览器演示
protocol/                  机器可读 schema、方法表、真实消息样例
examples/python/           不写前端的提供者与验收探针
examples/trafficmonitor/   TrafficMonitor 本机只读插件桥接示例
skills/wincraft-provider/  面向 Agent 的提供者逐课教程与仓库校验脚本
reference/exomind/         来源定位、迁移边界、窗口源码摘录
docs/                     产品、架构、协议、安全、验证、迁移与路线
evidence/assistant-run/   制作阶段浏览器与离线契约检查原始记录
evidence/local/           本地 Codex 实测命令、修复与验证矩阵
```

## 刻意暂不实现

组件级多写者借用、CRDT、长期存档与常客绑定、插件市场、任意代码执行、完整 Adaptive Cards/A2UI 兼容、鼠标跟随/外部窗口附着、游戏引擎/桌宠、原生 TLS/LAN 服务、浏览器 Origin 开放、全平台原生兼容，均不在本轮已实现能力中。

## 来源与许可

依据外心 `dev` 的固定快照 `ddb1ba1a6c1e0760af77b55d5659df44ad253b34`，提取并改造窗口创建/屏幕恢复的思路与部分几何代码；不迁入外心任务、档案、计时或数据库。保留来源许可与逐文件追溯。见 [来源说明](reference/exomind/PROVENANCE.md)、[LICENSE](LICENSE) 与 [许可备注](LICENSE-NOTES.md)。
