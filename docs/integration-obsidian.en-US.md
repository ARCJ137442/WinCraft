# Obsidian Workspace HUD

This is a generic Obsidian plugin example. It projects local file count, newest modification time, active tabs and pane counts from each enabled plugin instance, plus a 25-minute focus timer, into a WinCraft floating window. The Provider can request timer start, pause, resume, or reset and can ask the Host to activate an existing Obsidian window matching the selected active tab.

## Install and start

1. Copy the full [`examples/obsidian-plugin`](../examples/obsidian-plugin/) folder to `.obsidian/plugins/wincraft-workspace-dashboard/` in every vault you want included.
2. Enable **WinCraft Workspace Dashboard** in Obsidian's community plugin settings.
3. Start WinCraft and copy the runtime descriptor path from the World Manager.
4. Double-click [`examples/launchers/start-obsidian-workspace.cmd`](../examples/launchers/start-obsidian-workspace.cmd), select that path in the setup window, and start the Provider.

If Python lacks `websockets`, the setup window asks before pip installs the sample requirements. It never installs them without confirmation. The Provider runs until its window closes or the Host exits.

## Local data and controls

Each plugin instance reads only vault file metadata and workspace pane metadata from Obsidian's Workspace API. It does not read Markdown bodies, Canvas contents, properties, or plugin settings. It writes a small local snapshot under `%LOCALAPPDATA%/WinCraft/ObsidianWorkspace/instances/` and removes its own snapshot and pending command when unloaded. The plugin uses Node's local filesystem API only for this cross-window bridge; it makes no network requests, sends no telemetry, and does not modify vault files.

The Provider accepts only fixed focus timer actions. A window switch button passes the active tab title as a bounded selector to WinCraft's native Host action. The Host only attempts to activate an existing Obsidian window; it does not launch Obsidian or execute a command or script.

The count means fresh **WinCraft Workspace Dashboard plugin instances**. Only Obsidian windows with the plugin enabled are included. Each instance supplies its own active tab. The Obsidian Workspace API reports the current workspace panes and cannot guarantee enumeration of other process windows where the plugin is not enabled.

Active tab titles can include personal note names. They remain in local plugin snapshots, the WinCraft Host, and the floating window. They are not written to public documentation, screenshots, or evidence.

API references: [Obsidian Vault API](https://docs.obsidian.md/Reference/TypeScript%2BAPI/App/vault) and [Vault events and plugin cleanup](https://docs.obsidian.md/Plugins/Events).
