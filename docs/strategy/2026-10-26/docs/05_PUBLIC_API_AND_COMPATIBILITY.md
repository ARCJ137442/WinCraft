---
{
  "doc_id": "docs__05_PUBLIC_API_AND_COMPATIBILITY",
  "title": "公共 API、兼容演进与错误语义",
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

# 公共 API、兼容演进与错误语义

## 现状与目标分开

当前线协议 0.3 严格相等协商；未知字段在部分 Rust 结构上被拒绝；版本、Schema、SDK 必须同步。[W-MODEL][W-PROVIDER]

本包不指定一个已经发布的 0.4。后续首先提出兼容 ADR，再决定版本：稳定核心（握手、授权、世界、场景、动作）与版本化能力扩展分开。不能直接把未知字段从“拒绝”改为“静默忽略”，因为安全字段被忽略可能改变意义。

## 推荐协商模型（PROPOSED）

握手声明支持的协议范围、必须/可选 capability；宿主返回选定协议、每项 capability 的版本及状态 `supported/unsupported/permission_required`。不支持的必须能力拒绝建立对应功能，可选能力明确降级。现有 0.3 客户端进入专门兼容路径，保持其消息语义；实验能力带命名空间与显式 opt-in。

Schema 版本、产品版本、线协议、Provider adapter 版本、主题格式、配置包格式独立记录。包示例使用 `draft-2026-10-26`，不能拿它当下一个线协议版本。

## 方法族与实现边界

现有 `world.* / scene.* / data.* / window.configure / action.result` 保持公开基线。拟议能力名如 `events.subscribe`、`registry.discover`、`scope.claim`、`shortcut.register` 是设计族名，不是已可调用端点。每个新增方法必须在同一个 PR 中带 Rust 类型、Schema、SDK、正反例、错误与权限声明。

供应者业务事件（Agent 状态、手机摘要、任务进度）首先作为 Provider 数据流，不能把所有领域字段增加进 Host 顶层方法。

## 五层结果

| 结果 | 能证明 | 不能证明 |
|---|---|---|
| received | 消息被解析/接收 | 有权执行 |
| accepted | 校验通过、意图已记录 | OS 或业务已完成 |
| applied | 对应原生/界面操作兑现 | 外部业务成功 |
| acknowledged | 提供者接受了交互 | 外部业务最终成功 |
| completed/failed/unknown | 权威业务明确结果，或结果仍未知 | 网络超时可以当作失败重试 |

新错误保留稳定 `code`，增加 `message_key` 与参数方便本地化；诊断详情不含凭据与业务正文。版本冲突可重新取快照后重算；超时、断线后的写操作先读取权威状态，不能盲目重放。

## 验证与兼容门

用现有 Python 客户端、固定 0.3 契约 corpus、新客户端三组测试。验证旧客户端不收到无法解码的新通知；optional capability 缺失时仍能完成基础窗口；撤销权限后不能借缓存继续调用。

接口承诺先用“实验/预览/稳定”标记，不在核心仍频繁改动时口头保证永久兼容。稳定化后要有弃用警告、迁移指南与至少一个已声明的兼容窗口；具体期限由维护者按能力与资源定，不在本包虚构日历。
