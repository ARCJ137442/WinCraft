# 来源与证据界限

核查日期：2026-10-26。只列真正影响本原型的材料，不将其他产品的 README 等同实测。

## 用户讨论

用户初始讨论与后续确认是产品需求来源：窗口/世界、方块组件、Rust/Tauri、业务外置、运行态重建、多读单写、先窗口级、自用管理器、非本机提供者、立即落地源码。初始讨论中未经查证的竞品唯一性说法不作为设计事实。

## 外心代码固定快照

仓库：https://github.com/exomind-team/exomind
提交：`ddb1ba1a6c1e0760af77b55d5659df44ad253b34`

- `src-tauri/src/commands/now_workbench_overlay_commands.rs`：创建/显隐/屏幕位置恢复；blob `8039b8c605e85b52a085b5efd2c1fa7fa9a4f60f`。
- `src/pages/NowWorkbenchOverlayPage.tsx`：分离窗口中的业务 UI、不同尺寸、启动 readiness 经验；blob `edefedc7eb69e428cf6c5982969555a3657f4e76`。
- `docs/development/now-workbench-overlay-release-debug-diagnosis.md`：历史诊断，不能据此断言当前仍有相同故障。
- `src/lib/adapters/timeblock-rt-adapter.ts`：GET 活动时间块及既有读写路由；blob `df7d2724ebf063ffc422528864ec586f80264def`。
- `src/lib/adapters/runtime-profile-scope.ts`：user_id 档案作用域；blob `cd461918e0699416ea77644ec8ce674f6135da9f`。
- `LICENSE`：原项目 CCOPL-1.0，blob `6e73a892c873e6244dcf669d38b5b56140b90f25`。

没有下载/打包外心整个仓库，没有改其远程分支，也没有运行其业务接口。

## TrafficMonitor 本机桥接

2026-10-26 本机只下载并暂存作者发布的 `V1.86 x64 Lite` 二进制包；没有替换 `Program/Tool` 中原有安装。Gitee 作者仓库的 [V1.86 发布页](https://gitee.com/zhongyang219/TrafficMonitor/releases)列出 x64 Lite；[GitHub release asset 清单](https://github.com/zhongyang219/TrafficMonitor/releases/expanded_assets/V1.86)公布 SHA-256 `d9774a64268f952b5cb88a1eead399f863f7d4ab64e945f19c096fed89cc1145`，本机 Gitee 下载哈希与之匹配。包内不含 `TrafficMonitor.sys`、`OpenHardwareMonitorApi.dll` 或 `LibreHardwareMonitorLib.dll`。

以 V1.86 标签的 [`TrafficMonitorDlg.cpp`](https://gitee.com/zhongyang219/TrafficMonitor/blob/V1.86/TrafficMonitor/TrafficMonitorDlg.cpp) 和插件接口头文件为准：主程序周期调用 `DataRequired()`，随后以 `OnMonitorInfo(MonitorInfo)` 传入上下行、CPU、内存和 GPU 读数。桥接因此从该回调生成本地快照，不依赖未必可用的 `OnInitialize` API 指针。实现/验收见 `examples/trafficmonitor/wincraft_bridge.cpp` 与 `evidence/local/validation-matrix.md`。

## 官方技术资料

- Tauri tray：https://v2.tauri.app/learn/system-tray/
- Tauri command/caller WebviewWindow：https://v2.tauri.app/develop/calling-rust/
- Tauri capabilities：https://v2.tauri.app/security/capabilities/
- Tauri window customization：https://v2.tauri.app/learn/window-customization/
- Axum WebSocket 0.8.9：https://docs.rs/axum/0.8.9/axum/extract/ws/index.html
- Rust borrowing：https://doc.rust-lang.org/book/ch04-02-references-and-borrowing.html

这些资料用于校对 API 与概念。未完成本机编译之前，不据此宣称组合后的程序可运行。

## 设计参照（本包未复制代码）

GlanceHUD 的 `docs/PROTOCOL.md` 提供模板/数据分离与外部推送启示；它的现有模块遇到已存在 ID 时忽略 template，与本项目的持续结构变更目标不同。

Rainmeter/Eww 提供组件拼搭和数据驱动参考；Adaptive Cards/A2UI 提供声明式宿主渲染参考。本项目不是它们的兼容实现，不能拿其能力作本项目已实现承诺。

原文参照：
https://github.com/harry18456/GlanceHUD/blob/master/docs/PROTOCOL.md
https://docs.rainmeter.net/manual/
https://elkowar.github.io/eww/
https://learn.microsoft.com/en-us/adaptive-cards/
https://github.com/google/A2UI
