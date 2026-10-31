# 模型额度悬浮窗

本 Provider 在一个 WinCraft 世界中显示已选来源的 Codex、DeepSeek 与 MiniMax 额度。每个来源独立显示状态、新鲜度、币种或周期；未知值不会变成零。当前来源由用户在小型配置窗口中点选增删。

## 双击启动

1. 启动 WinCraft，从托盘打开世界管理器，点击连接描述文件旁的“复制路径”。
2. 双击 `examples/launchers/start-model-quota.cmd`，把刚复制的路径粘贴到终端提示。
3. 在来源窗口里勾选 Codex 本机快照、DeepSeek API Key 或 MiniMax API Key；取消勾选就是移除该来源。
4. 启动后也可以在额度悬浮窗点“添加 / 管理来源”。如果服务商来源尚无 Key，面板只显示配置按钮，不占位置显示“未启用”或“无缓存”。

DeepSeek/MiniMax API Key 在遮蔽输入框里输入，仅放在当前 Provider 进程内存，不写设置文件、日志或 scene。未勾选的来源不会读取对应环境 Key，也不会发出请求。当前版本没有提供网页登录或 Mimo 来源；未实现来源不会显示成假的“在线”卡片。

## 来源边界

- **Codex 本机快照**：只解析本机近期 session/archived JSONL 尾部的 `token_count` rate limit 字段；不读会话正文、`auth.json`、状态数据库或网络。
- **Codex 在线额度（实验性）**：单独勾选后才从本机 `auth.json` 的必要字段构造固定只读 HTTPS GET；不是稳定公开 API。
- **DeepSeek**：固定 `GET https://api.deepseek.com/user/balance`，只投影有限余额字段。
- **MiniMax**：固定 `GET https://api.minimaxi.com/v1/token_plan/remains`，只投影有限额度窗口。

DeepSeek/MiniMax 使用 HTTPS、拒绝重定向、限制响应大小并清理错误信息。不要把 Key 放进命令行、WCP 包或截图。窗口关闭/宿主退出会结束本 Provider。

未安装 Python `websockets` 时，双击脚本会在启动前询问是否安装仓库的示例 requirements；不会静默安装。开发者也可用合成测试运行 `python scripts/model_quota_headless_smoke.py`。

完整英文说明见 [README.md](README.md)。
