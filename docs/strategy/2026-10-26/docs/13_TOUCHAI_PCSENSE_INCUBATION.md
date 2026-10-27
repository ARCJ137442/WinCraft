---
{
  "doc_id": "docs__13_TOUCHAI_PCSENSE_INCUBATION",
  "title": "TouchAI 与 PCSense：平台孵化而非功能吞并",
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
    "P-TOUCH",
    "TAURI-KEY"
  ]
}
---

# TouchAI 与 PCSense：平台孵化而非功能吞并

## TouchAI

本轮读取的 TouchAI README 描述快捷键召回、键盘操作、桌面上下文与工具扩展。[P-TOUCH] 这只是产品参考，不是“加上一个热键即可功能等价”的证明。它的文件、剪贴板、屏幕、模型调用与工具执行留在 TouchAI，WinCraft 只提供受控界面和授权后的原生交互能力。

本地先与协作者核对确切仓库/版本及真实功能表，再做差异矩阵：召回、文本输入、选区/文件附件、工具卡片、流式输出、取消、错误、模型切换、回到来源。每项标 present/partial/missing，不把漂亮界面当等价。

系统快捷键由 Host 统一注册、检测冲突、归属到 session/scope、失效清理，并允许用户改绑。不能要求一个特殊固定组合可用；不能为捕获快捷键扩展成键盘记录器。按下/释放与自动重复分开，麦克风按住说话等能力需额外权限。[TAURI-KEY]

## PCSense

作为用户设想的个人电脑 ERP，可以先用独立 Provider 管理任务、设备、服务、会话与轻量工作流。其数据库、资产逻辑、执行器不放进 WinCraft。先选择一个窄任务（如任务/设备状态总览）验证，不开发完整 ERP 才测试运行时。

“联机”是远端 Provider 与当前宿主的受保护连接，不是匿名访问别人桌面。PCSense 不应从运行时拿到所有系统管理权限；系统维护命令由独立受控执行层完成。

## 毕业路径

界面声明、主题、文案、业务 Provider 与授权分别可导出。独立 APP 可以继续连接 WinCraft，也可以在许可允许并完成审查后复用核心/渲染器；不自动复制上游代码改许可。导出不得含 token、租约或用户数据。

毕业门不是“做大了就搬”：若平台缺失大量业务专用交互、部署需完全独立或资源模型不匹配，可选择独立 APP；若公共契约继续合适则不必毕业。报告功能/运维/许可代价，让创作者自主选择。

## 第一方投入边界

提供一个能够被替换的示例与接口，不承诺维护 TouchAI 克隆或 PCSense 全业务。验证目标是“该来源能否无需宿主补丁构造自己的界面”，不是“WinCraft 能否取代它”。
