# 制作环境实际验证记录

日期：2026-10-25。对应交接版本：0.1.0-alpha.1。这是原型制作环境记录，不是本地 Codex 的最终验收报告。

## 本机 Windows 验证摘要（2026-10-26）

以下结果来自当前 WinCraft 工作目录中的实际执行；原始制作环境记录保留在本文件下文，不再代表当前状态。

| 范围 | 状态 | 已证明的范围 |
|---|---|---|
| UI/离线契约 | PASS | `npm run check`：17 项 Node 测试、8 类离线契约；Edge smoke 16 项 mock-provider DOM 检查，含 `text_selectable` 默认、局部样式覆盖与标题栏不可选，不代替原生输入验收 |
| Python provider/Agent skill | PASS | 15 项 Python provider 单测；provider skill 自检 12 个仓库引用；真实 TrafficMonitor 与 Obsidian Workspace provider 启动/读取链路分开记录 |
| Rust workspace | PASS | rustfmt、core/server/desktop 检查、workspace Clippy `-D warnings`；debug core/server 30 项、workspace optimized 38 项测试通过 |
| Tauri release | PASS | `npm run desktop:build` 成功；独立执行 `E:\tmp\wincraft-target-text-selection-20261026\release\wincraft-desktop.exe --open-manager`，真实 TrafficMonitor 与 Obsidian provider 接入；不经 Vite 代理 |
| 当前 descriptor ACL | PASS（单文件、单账户） | 从当前宿主输出的路径对 ACL 元数据执行只读检查：owner 是当前用户，没有 Everyone/Authenticated Users/Users/Guests broad-read grant；没有读取文件内容 |
| 真实协议 | PASS | 最新 release Host 上 `lease_probe.py` 19 项通过：严格 0.3 握手、旧 0.2 拒绝、文本选择默认/读写、认证/Origin、读写授权、动态/原子 patch、租约过期、断线 fencing、慢消费者 |
| TrafficMonitor | PASS | 作者 V1.86 x64 Lite 隔离暂存副本经 `OnMonitorInfo` 持续发布；provider 接入当前 release，状态在线、版本 1.8.6.0、generation/revision 递增；证据不含遥测数值 |
| Obsidian Obsidian Workspace | PASS | 只读 provider 连到当前 release；Obsidian Workspace 0.14.7 投影 5 个关注项和 4 组提醒，native report 为 applied；未写笔记/插件设置，证据不含标题 |
| GitHub | PASS | `ARCJ137442/WinCraft`、默认分支 `dev`、`origin` 已建立；按用户最新决定仓库公开。源码首个提交 `c70ba44`、路线图 `3661dce`、文本选择功能 `73c3e20` 均已在远端 |
| 用户观察 | PASS（此前版本） | 用户确认托盘图标/菜单可用、悬浮窗可见且可拖动；最新替换后的 release 尚未要求用户重复做这些手工观察 |
| 原生人工门 | NOT_RUN | 最新 release 的文本选取鼠标手势、focus-demo 按钮回执、像素级 manager 滚动条、tooltip hover、不同 DPI/显示器、休眠恢复、IME 与 revision-conflict UI 仍需人工/专用环境验收；click-through rescue/hold 细节见本机矩阵 |
| ExoMind | BLOCKED（用户暂缓） | 未读取连接信息、未猜端口/档案、未调用 API |

独立 release 为 11,218,432 字节，SHA-256：`b04beafe2ffd4320373e4a750c4fc6d0b78e74f9808ae1d802faf98089945e38`。实际命令/退出码和脱敏状态在本机 `evidence/local/`；该目录按设计不进入提交，不记录 `.runtime.json` 内容、token、Obsidian 标题或 TrafficMonitor 遥测值。

## 已实际执行

| 项目 | 结果 | 证据/范围 |
|---|---|---|
| TypeScript 5.8.3 严格编译 | PASS | 实际源码编译为 ES2022，strict/noUncheckedIndexedAccess/noEmitOnError |
| Node.js v22.16.0 单元测试 | PASS，12项 | `evidence/assistant-run/ui-tests.log`，数据绑定/格式/属性安全等 |
| 离线契约检查 | PASS，8类检查 | `contracts.json`：JSON/TOML/Python语法、schema正反例、方法源码存在、无动态代码、路径依赖 |
| Chromium实际编译模块的DOM检查 | PASS，9项 | `browser-smoke.json`，同一 renderer、模拟provider，**非Tauri、非真实WS** |
| 许可原文 | PASS | 根LICENSE Git blob hash与ExoMind `6e73a892c873e6244dcf669d38b5b56140b90f25`一致 |
| 文件/文档完整性 | 见 `artifact-audit.json` | 相对文档路径与打包文件检查，非语义正确性证明 |

原始日志保存在 [evidence/assistant-run](../../evidence/assistant-run/)。浏览器截图也在该目录；它们只是实际前端代码的浏览器预览，不是Windows截图。

## 浏览器验证的精确边界

制作环境的 Chromium 策略拦截了 localhost 顶层导航。没有关闭或修改浏览器安全策略；检查脚本通过 `page.set_content` 放入宿主页面，并用内存 blob 加载**同一份实际编译后的 TypeScript 模块**，仅改写模块 import URL。Node 本地静态服务另经 HTTP 请求检查。环境使用 `WINCRAFT_OFFLINE_BROWSER=1` 选择这一明确标记的路径。

已验证：演示有标签、无关刷新不丢草稿与DOM身份、动态替换组件、输入回到模拟提供者、文字不作为HTML解析、过期世界禁用按钮、中文组合输入不中断、管理器fixture复用renderer、无浏览器运行时错误。

没有验证：Tauri IPC、CSP在真实Tauri环境的效果、Rust业务状态机、实际WS回执、托盘、置顶、穿透、显示器/DPI、native窗口可达性、真实外心或远程设备。

## 未执行／不能宣称完成

| 项目 | 状态 | 原因 |
|---|---|---|
| cargo fmt/check/test/clippy | NOT_RUN | 制作环境没有cargo/rustc；已写22个Rust测试，但不能计作通过 |
| Axum真实headless + lease_probe | NOT_RUN | Rust程序未编译，未用替代后端冒充 |
| Tauri 2开发构建与运行 | NOT_RUN | 无Windows桌面与Rust工具链 |
| 独立Windows release | NOT_RUN | 无可执行构建产物 |
| 实际网络握手/远端SSH | NOT_RUN | 仅协议/客户端源码，未连实际服务 |
| Python模拟provider业务循环 | NOT_RUN（真实连接） | AST检查不是运行链路 |
| 真实ExoMind RT桥接 | NOT_RUN | 本轮没有用户实际运行端口/档案/现场权限信息 |
| Windows ACL、多屏、IME原生路径 | NOT_RUN | 浏览器DOM验证不替代原生测试 |
| 性能、耗电、稳定性 | NOT_RUN | 没有可靠基准，不填造数字 |
| CI工作流 | NOT_RUN | 仅交付workflow文件，没有创建或运行远程Actions |

## 复现已执行部分

本地先 `npm install`；无需使用制作环境的编译器路径。制作环境因无网络依赖安装，使用预装 TypeScript 5.8.3，由 `TSC_JS` 指向本机既有编译器，**没有复制其node_modules或字体**到交接包。

```powershell
npm run test:ui
python -m pip install -r requirements-dev.txt
python scripts/check_contracts.py
python scripts/browser_smoke.py
```

浏览器脚本默认使用本地 dev URL；本机缺 Chromium 时可运行 Playwright 的浏览器安装命令，或用 `CHROMIUM_PATH` 指向本机 Chromium。依赖锁文件应由本机真实解析生成。本轮容器网络/DNS不可用，没有伪造下载成功。

## 后续记录方式

本地Codex将自己的结果写入 `evidence/local/`，新建本地验证摘要。保留本文件作为初始事实基线。修复后的代码需要复跑对应检查，不能把制作阶段的截图延续成修改后仍通过的证据。
