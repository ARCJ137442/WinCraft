# Obsidian Workspace Dashboard plugin

This generic example reports metadata from the **currently open Obsidian vault**:
file count, newest file modification time, workspace pane count, active pane title,
and a local 25-minute focus timer. It never reads note bodies, Canvas contents,
frontmatter, or plugin settings. The timer state is held in memory and can be started,
paused, resumed, or reset from WinCraft.

## Install

1. Copy this folder to each vault's `.obsidian/plugins/wincraft-workspace-dashboard/`.
2. In Obsidian, open **Settings → Community plugins → Installed plugins** and enable
   **WinCraft Workspace Dashboard**.
3. In WinCraft, open the World Manager and copy the connection descriptor path. Start
   `examples/launchers/start-obsidian-workspace.cmd` and choose the descriptor path.

Each plugin instance writes a small snapshot and reads one-shot timer commands in
`%LOCALAPPDATA%/WinCraft/ObsidianWorkspace/instances/`. Snapshots contain only that
window's metadata and timer state; the random instance ID distinguishes open Obsidian
workspaces without storing vault paths. Snapshot, command, and receipt files are
removed when that plugin instance unloads. A control request is accepted only for the
fixed focus timer actions in `main.js`; it cannot execute code or arbitrary commands.

The active pane title and tab titles can contain private note names. They remain on
the local machine and are never written to repository evidence. The Provider sends
them only to the local WinCraft Host for presentation.

## Limits

Obsidian's plugin API reports the current workspace and its panes. The window count is
the number of fresh plugin instances, so every Obsidian window or vault to include must
have this plugin enabled. It does not guess about windows where the plugin is absent.
WinCraft's native Obsidian activation action filters by the selected active pane title
and focuses an already-open window; ambiguous matches still follow the Host's existing
foreground-window rule.
