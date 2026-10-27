---
{
  "doc_id": "WORKTREE_ADOPTION",
  "title": "现有仓库整合与本轮重定基线记录",
  "updated_at": "2026-10-26",
  "last_verified_at": "2026-10-26",
  "baseline_commit": "6929056700b1ba6702288534579debc8a502c139",
  "protocol_baseline": "0.3",
  "status": "worktree-evidence",
  "audience": "maintainer, provider authors",
  "owner_role": "WinCraft maintainers",
  "review_trigger": "源码、计划状态或来源可见性变化时",
  "source_ids": ["W-BASELINE", "P-POPUP"]
}
---

# 现有仓库整合与本轮重定基线记录

本地工作树在 `6929056700b1ba6702288534579debc8a502c139`，与交接包冻结基线一致；开始前 `git status --porcelain=v1` 为空。未 fetch、checkout、reset 或改写远程。原始交接压缩包 SHA-256 为 `5798e3a56db9c7abd277675b1e9de21f6f828801540dd7e31e7615d8ba4d7401`；来源包的原始 `MANIFEST.sha256` 保存在本目录的 `SOURCE-MANIFEST.sha256`，当前可公开副本另有按本地内容重建的 `MANIFEST.sha256`。

本轮已从用户提供的交接目录整合 97 项包内容。唯一有意的来源修订是从 `sources/registry.json` 删除 `P-POPUP` 的受限仓库 URL；其运行语义摘要和来源 ID 保留。没有复制外部技能实现，也没有把本机安装路径写入仓库。受限来源契约由当前可读的本地版本核实；其上游版本号未声明。

## 本机基线环境

| 工具 | 版本 |
|---|---|
| Rust / Cargo | `rustc 1.93.0` / `cargo 1.93.0` |
| Node / npm | `v22.23.4` / `11.19.0` |
| Python | `3.11.4` |
| Git | `2.54.0.windows.1` |

本轮实际命令、退出码和覆盖范围记录在 `evidence/local/`；这里的版本和测试记录不声称完成真实 Windows UIA、用户键鼠或第三方 API 验收。交接包自检及本地源码测试是分开的证据。

## 来源与阻塞

- `popup-ask`：本机存在且可读，入口标识为 `structured`；核对到 1–4 题、每题 2–5 个预设选项、自动 `Other`、始终允许备注、`window_closed` / `cancel_button` / `escape_key` 取消原因，以及默认摘要与显式 JSON。来源代码不进入 WinCraft 仓库。
- SysTorch 与 TeamSense：本轮没有核实具体产品/接口版本或 endpoint；相关真实 adapter 继续 `BLOCKED`，不猜 URL。
- TouchAI、各 Harness 和其他公开参考：保留交接包引用，不据此声称本机已安装、已连接或已适配。

交接包内的 143 项产品验收初始为 `NOT_RUN`。只有由当前 WinCraft 源码、测试或实际宿主行为直接覆盖的项目才会更新状态；包内 34 项测试只验证交接资料自身。

## Popup 纵向切片进度

本轮为当前 0.3 host 增加了 capability-gated `textarea`、Escape/Ctrl+Enter 静态动作与选项组键盘行为；旧组件仍可照常使用。`examples/python/popup_ask_provider.py` 明确导入用户选定的本地 Popup-Ask 实现，复用 validate-only 和成功/取消结果序列化。成功时销毁临时世界，默认只把最后一次可观察的窗口位置/尺寸保存到本机 UI 偏好；测试时可传 `--position-store` 隔离该文件。问题文本、答案、token、descriptor 和旧 world/lease 均不进入位置偏好。

用户新增的可观察约束是：选择选项后 Tab 直达备注，Ctrl+Enter 带着当前备注草稿提交；单选方向键改变选项。编译后的 renderer DOM 检查通过，真实 Rust host 的 capability 与共享 fixture 通过 `lease_probe.py`。一个旧版本的本机 Popup 测试成功返回原 `--json` 形状并关闭窗口；新增键盘及复用位置行为仍需用户在当前打开的合成 Popup-Ask 窗口中人工验收。桌面自动化可以读取原生窗口，但此会话的 Windows helper 拒绝激活窗口，因此没有伪报键盘输入的原生 PASS。

B02-01 的 Host UI 国际化底座也已实现：Rust 内部管理器与 TypeScript chrome 共读中英资源，语言通过管理器的普通 action 切换，host 只持久化 locale ID，并以 `host/locale` 通知已打开窗口。缺失翻译有 key fallback 标记，外部 Provider 的文字保持 literal；后续已在先前单实例 Tauri manager 中实际切换英文并恢复中文。当前 lifecycle-enabled release 亦已启动；最新手工验收边界见仓库根 `docs/engineering/VALIDATION.md`。
