---
title: WinCraft 提供者进阶路线
updated_at: 2026-10-27
last_verified_at: 2026-10-27
protocol_baseline: 0.3
status: provider-design-guide
audience: agent, provider-author
---

# 像搭建 Minecraft 世界一样成为熟练提供者

WinCraft 提供者只发送声明式组件、数据和静态动作回执。业务真相留在提供者，宿主负责窗口、租约、权限、渲染和原生回执。按下面的顺序学习，每一层都可以在上一层失败时安全停止。

## 课程地图

| 层级 | 目标 | 入口 | 必须先检查 |
|---|---|---|---|
| 入门方块 | 连接、建世界、声明第一棵组件树 | `examples/python/provider_tutorial.py` 第 1 课 | `protocol=0.3`、`host_id`、写租约 |
| 变化与红石 | 在连接期间替换、插入、移动、删除组件；处理快照和事件 | 教程第 2 课、`examples/python/focus_demo.py` | `expected_revision`、稳定组件 ID |
| 交互回路 | 接收静态动作，执行业务操作，再返回 `action.result` | 教程第 3 课、`examples/python/popup_ask_provider.py` | 当前 world、lease epoch、action event ID |
| 主题与窗口 | 使用有限主题 token 和窗口属性；尊重人类拖动与接管 | 教程第 4 课、`examples/python/theme_demo.py` | `theme_tokens`、`window_properties` |
| 语义定位 | 在 provider 几何模式下使用工作区角落锚点；理解 DPI 换算和本地救援 | `docs/protocol.md`、`examples/python/lease_probe.py` | `window_property:anchor`、`geometry_control` |
| 观察与原生能力 | 订阅窗口状态；在用户点击后请求已登记应用动作 | `references/window-events.md`、`references/native-window-actions.md` | `window_state_events`、`external_window_actions` |
| 数据包式适配 | 将外部来源投影成可重建组件树，不复制来源业务状态 | `examples/python/trafficmonitor_provider.py`、`examples/python/obsidian-workspace.py` | 来源授权、数据新鲜度、只读边界 |

## 每层的完成证据

1. **入门方块**：真实 Rust host 接受 `world.create`，窗口关闭或断线后只清理自己的 world。
2. **变化与红石**：错误 patch 保留原 scene/revision；正确 patch 在同一 world 中生效。
3. **交互回路**：动作回执与业务完成分开；超时结果未知时不盲重试。
4. **主题与窗口**：缺少能力时在创建 world 前失败关闭；人类几何模式不会被提供者反复覆盖。
5. **语义定位**：先检查 `window_property:anchor`；切到 provider 几何模式后提交四角和逻辑边距；human 模式拒绝，救援后重新读取快照。
6. **观察与原生能力**：订阅不授予读权或写权；原生动作只由用户点击触发，失败不伪造成功。
7. **数据包式适配**：来源断开显示 stale/waiting，不把缺失值改成零；连接重建使用新 session/lease。

## 固定排错顺序

```text
descriptor → hello/host_id → capabilities → join/lease → snapshot → scene/data → interaction → ack
```

遇到 `STALE_LEASE`、`REVISION_CONFLICT`、`resync_required` 或 host 重启时，停止旧写入，重新握手、加入、读取快照，再从提供者真相重建。不要打印 runtime descriptor、令牌、真实笔记正文或业务遥测。

## 验证命令

```powershell
python skills/wincraft-provider/scripts/verify.py
python scripts/check_contracts.py
python examples/python/lease_probe.py --runtime "<manager 显示的实际 descriptor>"
```

浏览器预览、headless 探针和单元测试分别记录；只有独立 Tauri release 与人工 Windows 操作才能证明原生窗口行为。
