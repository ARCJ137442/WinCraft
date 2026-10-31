# Obsidian 工作区悬浮窗

这是一个通用 Obsidian 插件示例。它把本机文件数、最近修改时间、各个已启用插件实例的活动标签、工作区面板数和 25 分钟专注计时呈现在 WinCraft 悬浮窗中。提供者还能请求开始、暂停、继续或重置计时，并可点击对应标签尝试激活现有 Obsidian 窗口。

## 安装与启动

1. 把 [`examples/obsidian-plugin`](../examples/obsidian-plugin/) 整个目录复制到每个要纳入总览的 Vault 的 `.obsidian/plugins/wincraft-workspace-dashboard/`。
2. 在 Obsidian 的“设置 → 第三方插件”里启用 **WinCraft Workspace Dashboard**。
3. 启动 WinCraft 并从世界管理器复制连接描述文件路径。
4. 双击 [`examples/launchers/start-obsidian-workspace.cmd`](../examples/launchers/start-obsidian-workspace.cmd)，在启动窗口里选择该路径，再启动悬浮窗提供者。

如果 Python 环境缺少 `websockets`，启动窗口会询问是否用 pip 安装仓库列出的示例依赖；未确认前不会安装。提供者直到窗口被关闭或宿主退出前持续运行。

## 本地数据与控制

每个 Obsidian 插件实例只读取 Vault 文件元数据与 Obsidian Workspace API 返回的面板信息，不读取 Markdown 正文、Canvas 内容、属性或插件设置。它在 `%LOCALAPPDATA%/WinCraft/ObsidianWorkspace/instances/` 写入短小的本机快照文件，并在插件卸载时删除本实例的快照和待处理命令。插件仅为跨窗口桥接使用 Node 本地文件 API；不联网、不遥测，也不改写 Vault 文件。

提供者只接受固定的专注计时动作。窗口切换按钮将当前活动标签标题作为受限筛选条件交给 WinCraft 原生宿主；宿主只尝试激活已有 Obsidian 窗口，不启动 Obsidian，也不执行命令行或脚本。

窗口数表示新鲜的 **WinCraft Workspace Dashboard 插件实例数**。只有启用了该插件的 Obsidian 窗口会参与统计；独立窗口的活动标签由其插件实例分别提供。Obsidian Workspace API 提供的是当前工作区面板信息，不保证扫描未启用插件的其他进程窗口。

活跃标签和标题可能包含个人笔记名称。它们只留在本机插件快照、WinCraft Host 与悬浮窗内，不写入公共文档、截图或证据。

接口依据：[Obsidian Vault API](https://docs.obsidian.md/Reference/TypeScript%2BAPI/App/vault)、[Vault 文件事件与插件卸载清理](https://docs.obsidian.md/Plugins/Events)。
