---
{
  "doc_id": "docs__15_NATIVE_CAPABILITIES",
  "title": "原生能力路线：以扩展点验收，不堆 Win32 清单",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "proposal",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 原生能力路线：以扩展点验收，不堆 Win32 清单

当前基线优先复核 `docs/windows.md` 与实际 Windows release；本表是后续工作，不是已实现功能。

| 能力 | 首个用例 | 最小验证与边界 |
|---|---|---|
| 类型窗口事件 | 隐藏后重新召回、来源响应 | source/cause、取消订阅、最终状态与回声抑制 |
| 语义锚定与运动 | 贴工作区角落、跟随已授权目标 | 逻辑/物理坐标、多屏负坐标、DPI、屏幕拔插、速度/边界 |
| 焦点/Shell | 用户请求返回原应用 | request 而非 force；系统拒绝有回执，置顶与激活分开 |
| 快捷键 | TouchAI 召回、一次性语音 | 本机授权、冲突、释放、按下/抬起、用户改绑 |
| 区域输入 | 可交互卡片与穿透背景 | 命中区域版本、焦点/IME、不能制造不可关闭窗口 |
| 托盘/通知/AppBar | 信息摘要与用户选择的侧栏 | 默认一个宿主托盘；AppBar 占工作区，不能冒充普通浮窗 |
| DWM/材质/主题 | 原应用风格投影 | 逐系统验证、unsupported 明示、主题降级不变权限 |
| 捕获策略 | 用户显式选择分享可见性 | 不保证防截屏；不允许来源悄悄隐藏敏感操作 |
| 语音 | 主动问答/朗读 | 一次性许可、取消、设备/语言不可用与在线处理说明 |
| 窗口组 | 临时工作空间 | 保持独立世界 ID/租约；OS 操作部分成功不能假装原子 |
| 可访问性 | 大字号、读屏与键盘 | 实际 UIA 树与原生输入验收，不只 DOM |

旧“最小化”当前实现是隐藏，不必等价 Windows 原生 minimize。事件应表述实际发生了 hide 还是 minimize，不用同一个布尔状态冒充两种系统状态。

参考路线图中的微信黑图现场只是一条观察，不能推断应用调用了特定 API；不将其作为捕获策略通用证据。

## 平台外延

Core/Schema/Provider 尽可能平台中立，Native capability 带平台、OS 版本、权限与实测结果。macOS、Linux X11、Wayland 分别矩阵，不以 Tauri 编译成功宣布跟随/焦点/置顶组合等价。只发布实际验证过的构建；无环境的能力为 NOT_RUN/unsupported。

## 桌宠可能性

最小 POC 只证明受控素材/状态切换、窗口局部运动、减少动画、输入和关闭恢复。它不引入 Live2D 业务或游戏逻辑。若现有组件不足，新增可复用 renderer 扩展点前单独做资源/执行隔离设计；禁止临时用任意 HTML 绕过。
