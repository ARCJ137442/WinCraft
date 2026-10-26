# 从这里开始

这是可以交给本地 Codex **检验、修订、编译并跑通**的初版源码，不是只包含方案的空仓库，也不是已验收的 Windows 应用。

2026-10-26 本机已通过 Rust workspace 测试、Tauri release 独立启动，以及 TrafficMonitor x64 Lite 到真实 Tauri 世界的数据联调；这不等于全部人工原生验收完成。摘要见 [`docs/engineering/VALIDATION.md`](docs/engineering/VALIDATION.md)，机器专属的逐项记录在默认不提交的 `evidence/local/`。

## 给人的最短阅读路径

1. `README.md`：产品与交付边界。
2. `docs/product/DECISIONS.md`：哪些是用户决定，哪些只是本轮实施取舍。
3. `docs/engineering/VALIDATION.md`：已执行/未执行的真实状态。
4. `CODEX_HANDOFF.md`：本地代理任务入口。

## 给本地 Codex 的第一句话

把根目录 `CODEX_PROMPT.md` 的全文发送给它，并让它在本包解压目录工作。不要只发 ZIP 文件名，也不要只给一个相对于当前不存在目录的内部路径。

## 三种不同的“跑通”

**前端预览通过**：可信组件 renderer 可以画图、接收浏览器输入。不能证明协议内核和 Windows API。

**headless 真宿主通过**：编译真正的 Rust Engine/Axum，在真实 WebSocket 上验证租约、权限、重建与冲突。不能证明置顶、托盘、穿透与多屏。

**Windows 桌面通过**：Tauri 构建成功，真实 Python 提供者能搭建/控制原生世界，托盘管理器可接管并找回；release 同样经过检查。这才是本轮目标验收。

本机自动化要显式打开隐藏的管理器时，可启动 release EXE 并传入 `--open-manager`；不带参数时仍保持托盘优先。

## 不能跳过的纪律

不要将浏览器 mock 当后端，也不要因前端截图完成就宣布完成。不要把 Rust 编译失败当成“需要重写产品”的理由。先保留设计不变量，再最小修复。不要向远程仓库推送、改外心现有分支、覆盖用户安装版、开放公网监听或运行外心写操作，除非用户追加明确授权。
