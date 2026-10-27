---
{
  "doc_id": "docs__09_EPHEMERAL_POPUP_SYSTORCH",
  "title": "一次性交互：Popup-Ask 与 SysTorch",
  "updated_at": "2026-10-27",
  "last_verified_at": "2026-10-27",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "in-progress",
  "audience": "maintainer, Luna",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "实现、协议、权限、依赖或用户决定发生变化时",
  "source_ids": [
    "U-LATEST",
    "P-POPUP",
    "W-MODEL",
    "P-SYSTORCH-LOCAL"
  ]
}
---

# 一次性交互：Popup-Ask 与 SysTorch

## 精确对齐现有技能

本轮读到的团队实现名称是 `popup-ask`，用户称 `popup-question`。保留现有入口，不自行全局改名。输入为 1–4 题，每题稳定 ID、2–5 预设选项；系统始终增加 Other、允许 notes；关闭窗口是 cancelled。默认 stdout 是稳定文本摘要，只有 `--json` 才输出结构化 JSON；题目/选项/说明/预览保持用户语言。[P-POPUP]

技能语义是阻塞等待，不能因为换成 WinCraft 就变为无返回的通知。技能激活也不扩张宿主提问许可：不要在不该提问的场景自动弹窗，不得利用新 UI 绕过 Harness 自身安全审批。

## 实施：新增 transport，不重写问题逻辑

增加可显式选择的 WinCraft backend，复用原请求校验、结果归一和 stdout 输出。现有 Tk/原生路径保留为回退。Provider 打开独立临时世界、生成控件、收集选择与备注、确认终态并清理。为避免 Popup 业务专用 host API，平台提供 capability-gated 的多行 textarea 与静态选项按钮组语义；旧 0.3 host 缺少能力时客户端必须明确拒绝，不能退化成只看起来可用的控件。

WinCraft backend 在创建世界前占用一个 per-user-session Popup 槽。Windows 使用本机会话命名互斥体；同时调用会得到明确 busy 错误，提示从世界管理器查找现有窗口，不连接第二个 writer、不建第二个 Popup 世界、不抢焦点。Host manager 作为内部 operator 已能列出该世界；实际可见性仍要在 release 上人工验收。

2026-10-27 provider 回归覆盖成功 ACK 后单次销毁、重复 submit 不重复返回成功、取消/关闭/超时/断线/ACK未知与清理失败，以及只保存 host snapshot 中可读的几何数据；单槽忙状态通过独立进程争用测试。另有一项延迟 10.2 秒才送达的提交回归，在 20 秒请求期限内仍完成 success，证明 provider 的整体等待独立于普通动作 ACK 时限。以上状态机用例使用 FakeClient；Popup 窗口成功/取消、键盘/IME/位置复用的真实 Tauri 路径仍为 `NOT_RUN`。

另以当前 Rust headless host 和安装的 Popup-Ask parser 对合成请求做了真实 WebSocket 测试：一个 provider 创建临时世界并按短超时返回 error，清理 RPC 确认成功；另一个并发 provider 在建立连接/创建世界前收到 busy error。headless 没有窗口 renderer，因此这只验证协议与互斥，不代替 Tauri 可见 Popup 的成功/取消/键盘验收。

兼容 transport 的进程退出码与原 skill 对齐：confirmed success 与用户取消是正常终态；超时、未知回执、busy 配额和传输错误输出 error payload 并以非零码返回，不把 error 当 answer。

默认推荐只影响展示，不预先提交选择。只有相应本人提交才能产出 success。来源/问题摘要/期限固定显示；危险授权操作使用不可被主题覆盖的可信条。预览支持键盘到达、屏幕阅读器与长文本，不靠颜色区分。

## 事件与整体等待分离

当前原生组件 `interaction` 的 ack 期限是 10 秒，而 Popup 等人可能长得多。按按钮选择、输入保存等局部动作先及时 ack；整体 question request 仍未完成。不得把 30 分钟等待映射成一个超时的 `action.result`。

## 本机真实窗口的交互约束

用户在实际 Tauri Popup-Ask 窗口中补充了三项要求：成功提交后销毁本次临时世界；下次提问恢复最近一次可读的原生位置/尺寸，但新建 world 与 lease；选项提交后按 Tab 直接到备注，Ctrl+Enter 将当前备注草稿和最终答案一起提交。提供者仅把位置/尺寸保存为本机 UI 偏好，不能存题面、答案、租约或旧 world ID。选项使用单一 Tab 停靠点与方向键导航；窗口仍由人类移动和调整。

当前实现用授权 host 的 `window.position` 观察值更新本机 Popup-Ask 几何偏好。协议及 native report 必须能给出实际观察几何；若位置未观测到，不写入猜测值。真实多显示器/DPI 后重新呈现仍需 Windows 人工验收。

| 事实 | 兼容输出/内部结果 | 恢复 |
|---|---|---|
| 明确提交且源请求仍有效 | success，稳定摘要/JSON | 一次返回；不重复业务提交 |
| 用户关闭/取消/Escape | cancelled，保留原 reason | 不是 error，不自动再弹 |
| 宿主断线/不可用 | transport failure（映射原 error 或显式回退） | 先使旧世界/请求失效，再开备用 UI，避免双答 |
| 请求方撤销/过期 | 内部 cancelled/expired | 兼容层如无法无损表达须版本化，不能伪造 success |
| 回复已发送但回执未知 | unknown outcome | 查权威 request 状态，不能猜成功或重送批准 |

必须测试 submit 与 close、timeout、disconnect 同时发生的竞争；绑定 request revision 与 lease epoch，旧窗口不能回答新问题。用户接管或切换来源后明确取消或重新授权。

## SysTorch 两个方向

**开始界面**：人类作为调用方选择目标、参数与范围，生成启动请求；SysTorch 才决定是否可执行。WinCraft 不是工作流后端。

**决策界面**：SysTorch/Agent 已有请求需要人类裁决，呈现依据、代价与选项；人类回复回到原请求；WinCraft 不替 SysTorch 推导结论。

两类都使用相同组件、主题和生命周期，但启动操作、决策结果及幂等键归原系统。只读定位到本地 SysTorch（原 Jev Switch）M1 候选 API：`POST /v1/systorch/decisions` 创建；caller token 仅能读取/取消自己的任务，回答接口 `POST /v1/systorch/decisions/{id}/answers` 只允许 `local-owner`。因此 WinCraft provider 只做显式发起、只读追踪/结果投影与显式取消，绝不传递主人密钥或代替 SysTorch 回答。候选代码与契约在来源工作树未提交、未发行；不等同稳定 API。B03-03 仍依赖 B03-02，真实运行验证还需要明确地址和受管理 caller token；目前只记录接口事实，不声称已连接。

## 最小验收故事

一个真实 popup 调用在 WinCraft 中显示两项和 Other/notes；用户填写中文备注后提交，调用方获得与旧 transport 等价结果；第二次按关闭得到 cancelled；第三次断开 Host，调用方有明确错误而非一直挂死。所有临时世界清理，不残留租约，不推进依赖未决答案的操作。
