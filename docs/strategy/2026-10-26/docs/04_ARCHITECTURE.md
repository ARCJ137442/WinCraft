---
{
  "doc_id": "docs__04_ARCHITECTURE",
  "title": "架构与代码接线：不重写宿主，不把业务塞进内核",
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
    "W-TREE",
    "W-MODEL",
    "W-TRANSPORT",
    "W-PROVIDER"
  ]
}
---

# 架构与代码接线：不重写宿主，不把业务塞进内核

## 六个职责层

```text
来源应用 / 自动化 / Harness / 手机摘要服务
        │ Provider-owned business & credentials
        ▼
适配器 / SDK / 环境规划器（外部、可撤销）
        │ 声明、数据、请求回执
        ▼
公共 API / 认证 / 发现 / 能力协商 / 订阅
        ▼
Rust Core：世界、作用域、版本、租约、资源生命周期
      ↙                                     ↘
可信声明式 Renderer                    Native adapters
组件、主题、i18n、a11y                  窗口、快捷键、OS 回执
```

内部管理器和教程通过同一组件/动作体系构造，但本机 operator 授权来自可信宿主，不能经网络自报角色获得。

## 对“宿主源码目前不需要改”的解释

采用的实施解释是：**不为某个提供者定制或分叉宿主，不另起一种渲染器；新增公共 API 和通用原生能力所必要的最小代码改动允许纳入核心批次。**否则事件、主题、细粒度租约不可能凭空出现。这个解释作为 `D-HOST-SCOPE` 架构决定记账，不冒充用户说过“永不改任何宿主文件”。

## 当前代码地图

| 现有路径 | 当前职责 | 计划中的改动入口 |
|---|---|---|
| `crates/wincraft-core/src/model.rs` | 协议版本、窗口与模型 | 类型化能力、主题引用、作用域；不放业务字段 |
| `crates/wincraft-core/src/engine.rs` | 权限/世界/版本裁决 | 作用域租约、快照读、资源撤销与 CAS |
| `crates/wincraft-core/src/scene.rs` | 组件树、结构验证 | 槽位边界、主题/文案引用验证 |
| `crates/wincraft-core/tests/invariants.rs` | 核心不变量 | 父子撤销、跨范围禁止、取消与版本测试 |
| `crates/wincraft-server/src/hub.rs` | 会话与方法/事件分派 | 发现注册、事件类型、backpressure 和授权门 |
| `crates/wincraft-server/src/transport.rs` | 回环服务、鉴权、WS | 保持现有安全门；按能力扩展不放开 Origin |
| `crates/wincraft-server/src/self_provider.rs` | 管理器自用 | 权限/主题/语言/教程视图复用 |
| `apps/desktop/src-tauri/src/windows.rs` | 原生窗口兑现 | 注册式事件、快捷键、焦点/锚定；按平台分支 |
| `apps/desktop/src-tauri/src/main.rs` | 托盘、IPC、启动 | 仅装配通用服务、可信管理入口 |
| `apps/desktop/src/{renderer,bindings,types}.ts` | 可信渲染与绑定 | 文案引用、主题 token、组件身份和可访问性 |
| `protocol/`、`examples/python/client.py` | 契约与客户端 | 新旧兼容、样例、自动生成接口检查 |
| `skills/wincraft-provider/` | Agent 接入教材 | 新手/专业路径、更新时间、合成与真实证据标记 |

路径按固定仓库树与已读源码定位，不意味着全部文件已逐行审计。Luna 开始任务时通过符号搜索核对真实调用链；不得只按文件名机械插入代码。[W-TREE][W-MODEL][W-TRANSPORT]

## 资源生命周期原则

新订阅、快捷键、主题观察、数据引用与临时世界都注册为可清理的 resource。会话结束、作用域撤销或设置禁用时，沿所属关系撤销。建议内部 Rust 使用 RAII handle/显式 dispose；不能因为 Rust 对象被释放就假定远端业务操作已撤回。

配置可持久化的是用户选定的模板、语言、主题、能力需求；会话 token、lease、epoch 与 OS 窗口句柄不可作为下次启动的有效授权。

## 宿主边界不外溢

不加入通用 shell、浏览器 Cookie 导出、任意 URL WebView、音频转发或遍历全部文件。外部提供者可以使用其本身经用户授权的工具，宿主只管自己的能力。业务 Adapter 的失败不应结束全部世界；共享进程故障域要如实记录，不能称为多租户安全沙箱。
