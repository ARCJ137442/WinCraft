# 原生窗口能力矩阵

**“接线”描述实现覆盖范围，不单独代表运行通过。** 可提交的本机验证摘要见
[`engineering/VALIDATION.md`](engineering/VALIDATION.md)；机器专属细项位于默认不提交的 `evidence/local/validation-matrix.md`。

| 能力 | 当前状态 | 语义/限制 |
|---|---|---|
| 多世界与托盘宿主 | 接线 | 一个宿主管理多个 WebViewWindow；并非每世界独立应用 |
| 标题/逻辑尺寸 | 接线 | 宽 160–2400，高 80–1800；原型限额可后续调整 |
| 桌面物理位置 | 接线 | 可负坐标；离屏/Windows 隐藏哨兵值回工作区右下角 |
| 置顶/显隐/任务栏/装饰 | 接线 | `visible` 默认显示；最小化仅隐藏、不销毁 world/lease，provider 可配置，管理器可恢复 |
| 自定义标题栏 | 接线 | 默认显示、固定在滚动工作区外；provider 可通过 `title_bar_visible` 隐藏/显示；X 仍执行关闭语义 |
| 人类拖动 | 接线 | 经自定义 surface_drag 验证 human 模式 |
| 提供者控制几何 | 接线 | 显式 provider 模式；用户默认可调整宽度的 human 模式下，provider 不得覆盖位置/尺寸 |
| 点击穿透 | 接线 | 默认关闭；provider 可配置；全窗穿透时按钮不可点击，依赖管理器/托盘接管恢复 |
| 悬浮面透明度 | 已有 CSS 渲染 | 默认 surface_opacity=0.8，provider 可用 window.configure 调整；OS 原生窗口背景保持透明 |
| 管理器超高内容 | 接线 | 标题栏、状态栏和页脚固定；manager scene 独立滚动，工具栏 sticky；窗口级滚动条隐藏 |
| 原生执行结果 | 接线 | pending/applied/error；可能部分原生调用先成功再失败，报告而非假装回滚 |
| 人类移动回写投影 | 接线 | 不保存磁盘；已观测几何不回声式重设造成拖动抖动 |
| 多屏位置恢复 | 部分接线 | 创建/应用配置/托盘找回检查工作区；自动拔屏全周期仍需扩展 |
| 光标跟随 | 未实现 | 后续宿主本地行为引擎；不在提供者每帧传坐标中硬凑 |
| 附着其他应用窗口 | 未实现 | 需 Win32 目标身份/生命周期/权限处理 |
| 调整焦点/快捷键/任意窗口探查 | 未实现 | 不把‘全部 Windows 能力’写成已覆盖事实 |
| 跨平台桌面 | 未验收 | 核心跨平台设计不等于原生行为同等可用 |

## 2026-10-26 本机实测摘要

- `npm run desktop:build` 成功；独立 release EXE 使用显式 `--open-manager` 参数启动后，实际出现“窗构 · 世界管理器”。不带该参数时仍保持托盘优先。
- 最新 release 接入真实 TrafficMonitor x64 Lite provider，原生世界标题为“TrafficMonitor · WinCraft”；可访问性树显示来源在线、版本 1.8.6.0 和下载/上传/CPU/内存/GPU 组件。遥测数值不写入证据。
- `lease_probe.py` 对同一个 release Host 完成 13 项真实协议检查，包含租约过期/断线 fencing、慢消费者和正向 `scene.patch` 网络操作。
- 当前 release 的 provider 可通过真实 WebSocket 隐藏/显示窗口而不改变 lease epoch；隐藏不销毁世界，管理器也为隐藏世界提供恢复入口。
- 用户此前确认托盘/菜单可用，悬浮窗可见且可拖动。不同 DPI、多显示器、click-through 救援、窗口属性逐项切换和最新 release 的像素级滚动条回归仍未完成。

原生资源状态与业务状态分离。收到一个版本化窗口意图后，监督循环尝试应用；失败保留错误，隔一定时间重试。窗口被操作员销毁后移除核心世界并关闭 native 资源。

public renderer 的权限只允许事件订阅及受 Rust 端标签约束的四个自定义 IPC。未开放通用窗口修改权限给前端；修改走核心，不能绕过所有权检查。
