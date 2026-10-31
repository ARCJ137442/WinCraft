# `.wcp` 提供者代码包

`.wcp` 现在可以承载两种相互隔离的包：已有的 `wincraft.pack.draft` 配置包，以及 `wincraft.provider-bundle` 本机提供者代码包。配置包仍只含蓝图，不会执行代码；提供者代码包会经过独立校验、预览、解包和逐次启动确认。

## 给用户的流程

1. 从仓库目录执行 `python scripts/build_provider_bundle.py`，生成合成测试包 `target/provider-bundles/wincraft-sample-provider.wcp`。
2. 打开 WinCraft 世界管理器，把 `.wcp` 文件拖进窗口。管理器自动填入路径并预览包的名称、版本、运行时、入口、展开大小与 SHA-256。
3. 点击“安装代码（仅解包）”。此时没有代码运行，也不会安装 Python 依赖。
4. 点击“运行此提供者”后会再次显示代码执行警告与入口；点击最终确认才启动子进程。

如需验证 Obsidian 插件，可运行 `python scripts/package_obsidian_plugin.py` 生成 `target/obsidian-plugin/wincraft-workspace-dashboard.zip`，按[安装指南](integration-obsidian.zh-CN.md)启用。Python Provider 依赖未安装时，Obsidian 启动器会先询问是否用 pip 安装示例 requirements。

## 包边界

代码包必须包含严格 JSON 文件 `wincraft-provider.json`，字段为 `kind`、`schema_version`、`id`、`version`、双语 `title` 和类型化 `entrypoint`。入口只接受 `.py`、`.js/.mjs` 或 Windows `.exe`；所有文件都必须是普通文件，路径、文件数、压缩大小与展开大小都有上限。拒绝符号链接、重复路径、路径穿越、同版本覆盖，以及与预览摘要不一致的包。

安装只把经过校验的文件写入 WinCraft 本机 Provider store。启动不经过 shell、不自动安装依赖、不会继承任意环境变量，并隐藏运行时控制台；关闭 WinCraft 时会结束由本次 Host 启动的 Provider 进程。Python、Node 与 `.exe` 都收到标准参数 `--runtime <descriptor-path>`。每次启动都需要用户确认。

这不是代码沙箱。用户确认后，提供者代码会在当前用户权限下运行，可以读取用户允许访问的文件和网络，并能读取连接描述文件中的 bearer token，从而行使该连接允许的 WinCraft 操作。只运行来源可信、代码已检查的包；请勿把 runtime descriptor、其内容或真实业务快照写入包、提交或证据。

## 给提供者作者

清单示例与打包实现位于 `examples/provider-bundle-sample/` 和 `scripts/build_provider_bundle.py`。入口程序必须接受 `--runtime <path>`，自行校验 Host id、协议、租约和能力，并清理自己创建的 world。配置包里的 `adapter` 仍只是引用；不能把脚本塞入蓝图或配置包来绕过新的代码执行确认。

当前格式用于本机原型验收，不是协议 0.3 的网络功能，也没有依赖管理器、签名发布或沙箱隔离。
