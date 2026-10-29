---
{
  "doc_id": "plan__TRACEABILITY",
  "title": "需求—规范—任务—验收追踪（生成视图）",
  "updated_at": "2026-10-29",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "generated-view",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "W-BASELINE"
  ]
}
---

# 需求—规范—任务—验收追踪（生成视图）

单一来源为requirements.json与tasks.json，不手改生成表。

| 需求 | 内容 | 来源 | 规范 | 任务 |
|---|---|---|---|---|
| R001 | 平台让人、程序、Agent同台创造，开箱即用而非裸WinAPI | latest | [01_CHARTER](../docs/01_CHARTER.md) | B01-01, B02-03 |
| R002 | Windows悬浮窗是起点，不把愿景限死；当前世界窗口映射不重写 | latest | [01_CHARTER](../docs/01_CHARTER.md) | B00-01, B11-03 |
| R003 | 保留Rust/Tauri、共享托盘宿主、可信渲染器，不采用Electron/Go | accepted | [04_ARCHITECTURE](../docs/04_ARCHITECTURE.md) | B00-01 |
| R004 | 普通提供者不提交前端源码、不按业务修改宿主；允许必要通用API改动 | latest | [04_ARCHITECTURE](../docs/04_ARCHITECTURE.md) | B01-01 |
| R005 | 业务真相外置，运行状态可重建；无永久世界提供者绑定 | accepted | [04_ARCHITECTURE](../docs/04_ARCHITECTURE.md) | B01-02, B07-01 |
| R006 | 连接后持续动态增删重排组件；不止首次模板注册 | accepted | [04_ARCHITECTURE](../docs/04_ARCHITECTURE.md) | B01-04, B07-04 |
| R007 | 用户本机接管最高，旧租约不能抢回，来源与原生结果诚实 | accepted | [06_OWNERSHIP](../docs/06_OWNERSHIP.md) | B01-02, B07-02 |
| R008 | Popup作为首个临时交互transport，复用团队技能输入输出 | latest | [09_EPHEMERAL_POPUP_SYSTORCH](../docs/09_EPHEMERAL_POPUP_SYSTORCH.md) | B03-01, B03-02 |
| R009 | Popup保留Other、notes、多选、中文、摘要/JSON与关闭取消 | latest | [09_EPHEMERAL_POPUP_SYSTORCH](../docs/09_EPHEMERAL_POPUP_SYSTORCH.md) | B03-01, B03-02, B03-04 |
| R010 | 长问题等待与10秒动作ack分离，结果不被晚到/重复消息改写 | engineering | [09_EPHEMERAL_POPUP_SYSTORCH](../docs/09_EPHEMERAL_POPUP_SYSTORCH.md) | B03-01, B03-02, B03-04, B08-04 |
| R011 | SysTorch延伸人类发起与人类决策，业务执行仍在来源 | latest | [09_EPHEMERAL_POPUP_SYSTORCH](../docs/09_EPHEMERAL_POPUP_SYSTORCH.md) | B03-03 |
| R012 | 主题适配源软件风格，同时保留真实来源与可信授权区 | latest | [10_THEME_I18N_ACCESSIBILITY](../docs/10_THEME_I18N_ACCESSIBILITY.md) | B02-02, B03-03 |
| R013 | TeamSense服务器负载/额度只读桌面投影，标明口径与新鲜度 | latest | [11_BROWSER_TEAMSENSE_VOICE](../docs/11_BROWSER_TEAMSENSE_VOICE.md) | B05-02 |
| R014 | ChatGPT/DeepSeek网页语义投影与官方API模式区分 | latest | [11_BROWSER_TEAMSENSE_VOICE](../docs/11_BROWSER_TEAMSENSE_VOICE.md) | B05-01, B05-03 |
| R015 | 系统语音一次性显式授权，取消可恢复，不默认常驻监听 | latest | [11_BROWSER_TEAMSENSE_VOICE](../docs/11_BROWSER_TEAMSENSE_VOICE.md) | B05-04 |
| R016 | 浏览器不获宿主token，不放宽Origin；受控桥接 | engineering | [11_BROWSER_TEAMSENSE_VOICE](../docs/11_BROWSER_TEAMSENSE_VOICE.md) | B05-01 |
| R017 | PCSense先孵化窄场景，再可毕业为独立APP | latest | [13_TOUCHAI_PCSENSE_INCUBATION](../docs/13_TOUCHAI_PCSENSE_INCUBATION.md) | B10-01, B10-02 |
| R018 | TouchAI集成热点键与功能映射，不把热键等同全部功能 | latest | [13_TOUCHAI_PCSENSE_INCUBATION](../docs/13_TOUCHAI_PCSENSE_INCUBATION.md) | B04-03, B04-04 |
| R019 | 配置包只封存配置/能力需求，不保存提供者二进制或保证其可用 | latest | [08_DISCOVERY_ADAPTIVE_PACKS](../docs/08_DISCOVERY_ADAPTIVE_PACKS.md) | B06-01, B06-04 |
| R020 | 授权的环境发现、自适应选择，有什么用什么，缺失能力降级 | latest | [08_DISCOVERY_ADAPTIVE_PACKS](../docs/08_DISCOVERY_ADAPTIVE_PACKS.md) | B01-03, B06-02, B06-04 |
| R021 | 包可引用适配程序；执行与导入分离、计划可审阅、不隐式运行 | latest | [08_DISCOVERY_ADAPTIVE_PACKS](../docs/08_DISCOVERY_ADAPTIVE_PACKS.md) | B06-02 |
| R022 | 导出不得包含token/租约/隐私，授权不能跨机器继承 | accepted | [08_DISCOVERY_ADAPTIVE_PACKS](../docs/08_DISCOVERY_ADAPTIVE_PACKS.md) | B06-01, B06-03 |
| R023 | 多Harness同窗聚合：Claude Code、Codex、OpenCode、DSH、omp | latest | [12_HARNESS_ACTIVITY](../docs/12_HARNESS_ACTIVITY.md) | B08-01, B08-02, B08-03 |
| R024 | 会话动态加入退出、实例身份、来源状态、父子关系与待办 | latest | [12_HARNESS_ACTIVITY](../docs/12_HARNESS_ACTIVITY.md) | B01-03, B08-01, B08-02, B08-03 |
| R025 | 观测不等于批准；执行批准走来源官方机制与独立授权 | engineering | [12_HARNESS_ACTIVITY](../docs/12_HARNESS_ACTIVITY.md) | B05-03, B08-01, B08-04 |
| R026 | 所有权从世界到组件子树再到类型状态槽，不能直接共享任意JSON全局写 | latest | [06_OWNERSHIP](../docs/06_OWNERSHIP.md) | B07-01, B07-03, B07-04, B08-03 |
| R027 | 多读不可变快照与单写租约；Arc/Mutex仅启发高级受控仲裁 | latest | [06_OWNERSHIP](../docs/06_OWNERSHIP.md) | B07-01, B07-03 |
| R028 | 父子撤销、跨子树操作与局部revision避免互扰 | engineering | [06_OWNERSHIP](../docs/06_OWNERSHIP.md) | B07-02, B07-03, B07-04 |
| R029 | 公开文档分小白/提供者/内核层，术语一致 | latest | [21_DOCUMENTATION_CONTRACT](../docs/21_DOCUMENTATION_CONTRACT.md) | B00-02, B02-01 |
| R030 | 更新时间、核验日期、源码/协议版本、证据级别落盘规则 | latest | [21_DOCUMENTATION_CONTRACT](../docs/21_DOCUMENTATION_CONTRACT.md) | B00-02, B11-04 |
| R031 | 国际化前置：中英入口、ID不翻译、语言与格式正确 | latest | [10_THEME_I18N_ACCESSIBILITY](../docs/10_THEME_I18N_ACCESSIBILITY.md) | B02-01 |
| R032 | 主题/翻译缺失有降级，键盘IME读屏原生验收 | engineering | [10_THEME_I18N_ACCESSIBILITY](../docs/10_THEME_I18N_ACCESSIBILITY.md) | B02-01, B02-02, B02-04, B05-04 |
| R033 | 社区可分享开放格式；官方不先建市场/awesome网站 | latest | [02_PRODUCT_AND_ECOSYSTEM](../docs/02_PRODUCT_AND_ECOSYSTEM.md) | B06-01, B06-04, B10-04, B11-04 |
| R034 | 桌宠/Live2D仅可能性，官方不做养成业务或完整角色生态 | latest | [15_NATIVE_CAPABILITIES](../docs/15_NATIVE_CAPABILITIES.md) | B10-03 |
| R035 | 教程世界、设置、管理器dogfood公开组件，不泄漏operator权限 | latest | [17_TUTORIAL_DOGFOOD](../docs/17_TUTORIAL_DOGFOOD.md) | B02-03, B02-04 |
| R036 | AndroMorph通知摘要到PC，跟Harness待办合并，但不声称已实现外部通知读取 | latest | [14_ANDROMORPH_TRANSPORT](../docs/14_ANDROMORPH_TRANSPORT.md) | B09-01, B09-02, B09-03 |
| R037 | 传输论/中继/飞书/LAN/BLE/WiFi/USB在外部transport，Core不承担路由网络 | latest | [14_ANDROMORPH_TRANSPORT](../docs/14_ANDROMORPH_TRANSPORT.md) | B09-01, B09-04 |
| R038 | 多设备认证、TTL、重复/乱序、撤销与端到端结果语义 | engineering | [14_ANDROMORPH_TRANSPORT](../docs/14_ANDROMORPH_TRANSPORT.md) | B09-01, B09-03, B09-04 |
| R039 | 通知只读先行，摘要带出处，消息内指令不成为批准 | engineering | [14_ANDROMORPH_TRANSPORT](../docs/14_ANDROMORPH_TRANSPORT.md) | B09-02, B09-03, B09-04 |
| R040 | Mod与任意宿主代码加载暂不做 | latest | [03_REFERENCE_DECISIONS](../docs/03_REFERENCE_DECISIONS.md) | B01-02, B06-01 |
| R041 | VSCode优先、DSH/Cordis生命周期、Obsidian插件UX参考；不机械照搬MC | latest | [03_REFERENCE_DECISIONS](../docs/03_REFERENCE_DECISIONS.md) | B00-03, B01-02 |
| R042 | 稳定可扩展内核、公共API优先，业务和集成在提供者 | latest | [04_ARCHITECTURE](../docs/04_ARCHITECTURE.md) | B01-01 |
| R043 | 许可CCOPL保留不变，上游署名不删，不擅自改MIT | latest | [20_GOVERNANCE_RELEASE_BRAND](../docs/20_GOVERNANCE_RELEASE_BRAND.md) | B00-02, B11-04 |
| R044 | 未来外心团队集体维护，星林/ARCJ137442是协作方向而非已授予角色 | latest | [20_GOVERNANCE_RELEASE_BRAND](../docs/20_GOVERNANCE_RELEASE_BRAND.md) | B11-04 |
| R045 | 安全模式借鉴Obsidian，但不能当真实权限沙箱 | latest | [16_SECURITY](../docs/16_SECURITY.md) | B01-03 |
| R046 | macOS/Linux是未来实证目标，Tauri不保证原生行为等价 | latest | [15_NATIVE_CAPABILITIES](../docs/15_NATIVE_CAPABILITIES.md) | B11-03 |
| R047 | 公众release后续按证据发版，不私改发布渠道 | latest | [20_GOVERNANCE_RELEASE_BRAND](../docs/20_GOVERNANCE_RELEASE_BRAND.md) | B11-02, B11-04 |
| R048 | WinCraft暂名、WinC可简称、窗构待定；不重命名仓库/包/协议 | latest | [20_GOVERNANCE_RELEASE_BRAND](../docs/20_GOVERNANCE_RELEASE_BRAND.md) | B00-02, B02-01 |
| R049 | Minecraft只借模型，艺术风格独立，不暗示官方关联 | latest | [20_GOVERNANCE_RELEASE_BRAND](../docs/20_GOVERNANCE_RELEASE_BRAND.md) | B02-02, B11-04 |
| R050 | 低门槛高上限宽路径可组合，成功衡量独立创作者接入成本 | accepted | [02_PRODUCT_AND_ECOSYSTEM](../docs/02_PRODUCT_AND_ECOSYSTEM.md) | B02-03, B04-04, B06-04, B10-01, B10-04 |
| R051 | 稳定版本与能力协商，保留已发布0.3行为或提供明确迁移 | accepted | [05_PUBLIC_API_AND_COMPATIBILITY](../docs/05_PUBLIC_API_AND_COMPATIBILITY.md) | B01-01 |
| R052 | 声明式结构、状态、事件、动作、关系、权限的语法分离 | accepted | [04_ARCHITECTURE](../docs/04_ARCHITECTURE.md) | B01-04, B04-01 |
| R053 | 注册可撤销、断线可清理，事件类型/因果/背压明确 | accepted | [07_EVENT_ACTION_LIFECYCLE](../docs/07_EVENT_ACTION_LIFECYCLE.md) | B01-02, B04-01 |
| R054 | 语义锚定/运动由宿主本地执行，不每帧网络坐标 | accepted | [15_NATIVE_CAPABILITIES](../docs/15_NATIVE_CAPABILITIES.md) | B04-02 |
| R055 | 焦点请求与置顶/Shell分开，系统拒绝不能伪造成功 | accepted | [15_NATIVE_CAPABILITIES](../docs/15_NATIVE_CAPABILITIES.md) | B04-02, B11-02 |
| R056 | 窗口组保留各自租约，部分原生失败不冒充原子回滚 | accepted | [15_NATIVE_CAPABILITIES](../docs/15_NATIVE_CAPABILITIES.md) | B10-03 |
| R057 | AppBar/DWM/区域输入/捕获排除独立权限及POC | accepted | [15_NATIVE_CAPABILITIES](../docs/15_NATIVE_CAPABILITIES.md) | B10-03, B11-02 |
| R058 | 捕获排除不承诺保密，不悄悄隐藏共享内容 | accepted | [16_SECURITY](../docs/16_SECURITY.md) | B10-03 |
| R059 | SDK、验证器、模拟器、诊断与错误恢复示例齐全 | accepted | [05_PUBLIC_API_AND_COMPATIBILITY](../docs/05_PUBLIC_API_AND_COMPATIBILITY.md) | B01-01, B01-04, B08-01, B10-04 |
| R060 | 性能测量全进程树、尾延迟与泄漏，不用语言/体积代替实测 | accepted | [19_VALIDATION_AND_PERFORMANCE](../docs/19_VALIDATION_AND_PERFORMANCE.md) | B11-01 |
| R061 | 测试层分L0至L6，repo报告不等于本轮独立测试 | accepted | [00_BASELINE_AND_EVIDENCE](../docs/00_BASELINE_AND_EVIDENCE.md) | B00-01, B00-04, B03-04, B07-04, B11-01, B11-02 |
| R062 | 每批回滚、锁文件真实解析、旧提供者回归、单文件单写者 | accepted | [19_VALIDATION_AND_PERFORMANCE](../docs/19_VALIDATION_AND_PERFORMANCE.md) | B00-01, B00-02, B11-01 |
| R063 | 来源 API 的身份、版本和权限未经核实或仅存在于未发行候选时，保持缺口并绑定明确来源；不得同名替换或猜端点。 | engineering | [00_BASELINE_AND_EVIDENCE](../docs/00_BASELINE_AND_EVIDENCE.md) | B00-03, B03-03, B05-02 |
| R064 | 阶段闭环先Popup再扩，不一次改全系统，不重复询问已确定问题 | latest | [18_ROADMAP](../docs/18_ROADMAP.md) | B00-01, B00-04, B03-01, B03-04 |
| R065 | 远程数据发现不授予读写权限，设备存在不等于加入授权 | accepted | [16_SECURITY](../docs/16_SECURITY.md) | B01-02, B01-03, B05-01, B07-02, B09-01 |
| R066 | 资源配额/注意力预算与紧急救援，避免无限弹窗和快捷键抢占 | engineering | [16_SECURITY](../docs/16_SECURITY.md) | B03-02, B04-03, B05-04, B08-04 |
| R067 | 可重复计划与显式提交，用户覆盖优先级、防来回抖动 | engineering | [08_DISCOVERY_ADAPTIVE_PACKS](../docs/08_DISCOVERY_ADAPTIVE_PACKS.md) | B06-02, B06-03 |
| R068 | 已有业务不被吸收入内核，孵化项目可退出而非平台锁定 | latest | [13_TOUCHAI_PCSENSE_INCUBATION](../docs/13_TOUCHAI_PCSENSE_INCUBATION.md) | B10-01, B10-02 |
| R069 | 所有权教学解释实际快照/租约，不把Rust编译期模型当网络保证 | engineering | [06_OWNERSHIP](../docs/06_OWNERSHIP.md) | B02-01, B07-01 |
| R070 | 分享或公开不得泄漏私有技能全文、真实消息、账号或连接信息 | accepted | [20_GOVERNANCE_RELEASE_BRAND](../docs/20_GOVERNANCE_RELEASE_BRAND.md) | B00-02, B00-04, B06-04, B09-04, B11-04 |
| R071 | 扩展只通过明确扩展面；来源版本快速变化需复核与证据过期策略 | engineering | [03_REFERENCE_DECISIONS](../docs/03_REFERENCE_DECISIONS.md) | B00-03, B01-04, B08-02 |
| R072 | 窗口组/场景/蓝图/业务存档分别定义，不以世界隐喻偷偷持久化业务 | accepted | [08_DISCOVERY_ADAPTIVE_PACKS](../docs/08_DISCOVERY_ADAPTIVE_PACKS.md) | B06-01, B06-03, B10-02 |
| R073 | Popup提交销毁临时世界并复用上次人类窗口位置；单选后Tab到备注，Ctrl+Enter提交当前草稿 | accepted | [09_EPHEMERAL_POPUP_SYSTORCH](../docs/09_EPHEMERAL_POPUP_SYSTORCH.md) | B03-02 |
| R074 | 一个全局悬浮窗纵览用户选定的Harness来源与会话；首屏突出Codex并行会话量和Claude Code会话状态，可切换来源/实例/会话并渐进披露详情 | latest | [12_HARNESS_ACTIVITY](../docs/12_HARNESS_ACTIVITY.md) | B08-02, B08-03 |
