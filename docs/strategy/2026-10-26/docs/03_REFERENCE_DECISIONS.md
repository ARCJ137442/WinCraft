---
{
  "doc_id": "docs__03_REFERENCE_DECISIONS",
  "title": "业界参考：采纳机制，不复制产品",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "proposal",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "VS-MANIFEST",
    "VS-CONTRIB",
    "VS-HOST",
    "VS-TRUST",
    "VS-I18N",
    "X-DSH",
    "OBS-SEC",
    "RUST-BORROW"
  ]
}
---

# 业界参考：采纳机制，不复制产品

以下外部事实核查于 2026-10-26；详细 URL 与范围见 [来源注册表](../sources/registry.json)。一手资料的支持范围与 WinCraft 提案分开。

| 参考 | 资料支持的机制 | WinCraft 采纳 | 不照搬 |
|---|---|---|---|
| VS Code | manifest、contribution points、扩展宿主、工作区信任、l10n | 能力贡献声明、依赖区分、激活/清理、文案目录、兼容检查 | 不立即运行第三方 JS，也不把 extensionPack 自动安装行为当配置包语义 |
| DeepSeek Harness / Cordis | 服务、类型事件、可撤销 effects、profile 与 bundle 层 | 注册资源随生命周期撤销、依赖可用性、配置分层、服务提供/消费分离 | 不迁入 Electron/Node 主宿主，不宣称所有内核都应外部插件化；DSH 明示预览期会破坏兼容 |
| Obsidian | 限制模式停用第三方代码；社区插件权限不能细分可靠限制 | 本机信任开关、明确第三方风险、禁用后保留配置 | 限制模式不是沙箱；不照搬“插件继承全部宿主能力” |
| Rust | `&mut` 排他、共享引用、Arc 引用计数、Mutex 互斥 | 所有权范围、撤销代、快照与有界仲裁 | 网络不是 Rust 引用；Arc 不提供授权，Mutex 不提供分布式锁 |
| Chrome 扩展 | Native Messaging、允许的扩展来源、宿主注册 | 受控扩展桥接；凭据留在原生侧 | 不开放所有 Origin、不复制 Cookie 到新 WebView |
| Tauri | 按窗口/WebView 控制 IPC 能力；独立快捷键插件 | Rust 原生能力适配、受限 IPC、平台能力矩阵 | Tauri 支持多平台不等于所有窗口组合已跨平台验收 |

[VS-MANIFEST][VS-CONTRIB][VS-HOST][VS-TRUST][VS-I18N][X-DSH][OBS-SEC][RUST-BORROW][RUST-ARC][RUST-MUTEX][CHROME-NATIVE][TAURI-CAP][TAURI-KEY]

## 两个重要修正

“Minecraft 没有官方 API”不能作为泛化事实写入工程文档：不同版本和扩展渠道不同。本包只借用创造/组合隐喻，依赖与加载设计优先参考 VS Code、DSH 和现有源码。

“无特权核心”是 DSH 文档对其插件架构的表述，不是 WinCraft 应复制的安全政策。WinCraft 的本地接管、权限核验与系统授权根必须保留宿主权威，不能让外部 Provider 注册一个同名服务就替换。

## 参考的采纳门

每引入一种机制，先写清解决的重复问题、最小接口、谁拥有状态、卸载后清理什么、失败如何恢复。没有真实需求时，不以参考项目“已经有”为由增加依赖；不把实验性 API 当稳定保证。
