---
{
  "doc_id": "docs__10_THEME_I18N_ACCESSIBILITY",
  "title": "主题、国际化与可访问性：从第一批进入架构",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "in-progress",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "VS-I18N",
    "TAURI-CAP"
  ]
}
---

# 主题、国际化与可访问性：从第一批进入架构

## 主题不是任意前端代码

Provider 可选择主题 ID 与被允许的 token，让窗口贴合原软件的风格。允许颜色、字号、字重、圆角、间距、密度、动效强度等有限值；资源须经过类型、大小、来源和许可检查。不接受任意 CSS、HTML、JS、网络字体或可执行 SVG。

外观目标是“自然延伸”，不是冒充来源或系统审批。可信边框保留真实 Provider 身份、权限提示、来源状态和本地接管入口；危险操作的授权条不能被主题隐藏、改写为另一个应用或设成不可见。

有效配置建议为：平台安全/可访问性强制值 → 本机用户覆盖 → 世界用户选择 → Provider 建议 → 宿主默认。Provider 可给出审美方案，本机用户的高对比、减少动画和字号需求优先。优先级须编写单一合成函数与测试，禁止 UI 各处自行拼接。

## 国际化前置

稳定 ID、方法名与错误码不翻译；标题、按钮、菜单、错误说明、能力解释、教程与配置包展示字段进入资源字典。首批 `zh-CN`、`en-US`，后续语言无需改业务代码。默认依据用户明确选择/系统语言，fallback 到已说明的默认语言，不把翻译缺失显示为空。

Provider 可发 literal（保留原文）或 `message_key + args`；宿主不擅自用云模型翻译私人正文。包可带自己的命名空间字典，不能覆盖可信权限文案。数字、时区、日期、复数、长文本与 RTL 都是布局输入，不是字符串替换后的偶然结果。[VS-I18N]

不要把“文档英文版存在”当国际化完成。必须检查菜单、错误、原生托盘、教程、Schema description、示例和 Agent skill。翻译记录 `source_revision`；源文更改时标 stale，不能更新日期假装重新翻译。

当前实现将 TypeScript renderer 与 Rust 内部管理器共享的 host 文案放在 `apps/desktop/src/locales/{zh-CN,en-US}.json`。语言偏好只保存 locale ID 到本机 host UI 设置文件；管理器经由内部提供者动作切换。稳定动作/错误 ID 保持不变，外部 Provider 的 literal 题面、选项与业务内容不会被自动翻译。原生 Tauri/WebView2 的语言切换与布局仍需 release 走查。

## 可访问性

组件有 role、name、value、状态和可用动作；焦点顺序、键盘导航、Esc 退出、输入法组合以及大字号布局都必须测试。预览或主题编辑不应打断正在输入的草稿。

WebView DOM 能表达语义不等于真实 Windows UIA 树已验收。以 release EXE 检查读屏与键盘，记录 OS/WebView2 版本。无法使用鼠标时仍有接管/关闭路径。透明度不能压低到阅读信息失效；减少动画应覆盖桌宠类表现接口。

## 交付

本包 `examples/theme/` 与 `locales/` 仅供实现契约参考。B02 在现有 Renderer 加入主题/i18n 合成，不换前端技术、不暴露 CSS 注入；教程世界以同一通路验证主题切换与中英切换。


## 当前实现状态（2026-10-26）

本地 WinCraft 0.3 将 `scene.theme` 作为 `scene_features: ["theme_tokens"]` 可选能力接入。Token 仅包含六个经过类型、范围和前景对比度验证的值；无效 scene replacement 原子拒绝，旧 scene、revision、业务数据和租约保持不变。Renderer 只在 `.scene` 内容容器应用主题，标题栏、来源标识、连接状态、权限提示与接管区由 host 固定控制。

用户本机字体缩放使用 Ctrl+Shift+加号、Ctrl+减号与 Ctrl+0，储存在本机 localStorage 并优先于 provider 字号。OS `forced-colors` 与 `prefers-reduced-motion` 样式同样覆盖 provider tokens。主题结构、renderer DOM、字号快捷键与浏览器媒体模拟检查通过；当前 lifecycle release 的真实 Tauri host `lease_probe.py` 28 项通过，其中包括主题能力与无效主题原子拒绝，且 `native_windows=true`。实际 Windows 高对比、显示缩放、读屏与原生主题像素呈现仍待人工验收；结果见仓库根 `docs/engineering/VALIDATION.md`。
