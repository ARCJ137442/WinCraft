const { Plugin, Notice } = require('obsidian');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const os = require('os');

const SNAPSHOT_SCHEMA = 'wincraft.obsidian-workspace.v1';
const COMMAND_SCHEMA = 'wincraft.obsidian-workspace.command.v1';
const FOCUS_DURATION_SECONDS = 25 * 60;
const MAX_TABS = 16;

class WinCraftWorkspaceDashboard extends Plugin {
  async onload() {
    const localData = process.env.LOCALAPPDATA || path.join(os.homedir(), '.local', 'share');
    this.bridgeDirectory = path.join(localData, 'WinCraft', 'ObsidianWorkspace', 'instances');
    this.instanceId = crypto.randomUUID();
    this.snapshotPath = path.join(this.bridgeDirectory, `${this.instanceId}.json`);
    this.commandPath = path.join(this.bridgeDirectory, `${this.instanceId}.command.json`);
    this.receiptPath = path.join(this.bridgeDirectory, `${this.instanceId}.receipt.json`);
    this.focus = { state: 'idle', elapsedMs: 0, startedAt: null, durationSeconds: FOCUS_DURATION_SECONDS };
    await fs.promises.mkdir(this.bridgeDirectory, { recursive: true });
    this.unloaded = false;
    this.processingCommand = false;
    this.publishing = false;

    this.addCommand({
      id: 'start-wincraft-focus-timer',
      name: 'Start WinCraft focus timer',
      callback: () => this.startFocusTimer(),
    });
    this.addCommand({
      id: 'pause-wincraft-focus-timer',
      name: 'Pause WinCraft focus timer',
      callback: () => this.pauseFocusTimer(),
    });
    this.addCommand({
      id: 'resume-wincraft-focus-timer',
      name: 'Resume WinCraft focus timer',
      callback: () => this.resumeFocusTimer(),
    });
    this.addRibbonIcon('timer', 'Start WinCraft focus timer', () => this.startFocusTimer());
    this.registerInterval(window.setInterval(() => void this.processCommand(), 250));
    this.app.workspace.onLayoutReady(() => {
      if (this.unloaded) return;
      this.initializeVaultMetadata();
      this.registerInterval(window.setInterval(() => void this.publishSnapshot(), 2000));
      void this.publishSnapshot();
    });
  }

  initializeVaultMetadata() {
    const files = this.app.vault.getFiles();
    this.fileCount = files.length;
    this.latestFileMtime = files.reduce((latest, file) => Math.max(latest, Number(file.stat?.mtime) || 0), 0);
    this.registerEvent(this.app.vault.on('create', (file) => {
      this.fileCount += 1;
      this.latestFileMtime = Math.max(this.latestFileMtime, Number(file.stat?.mtime) || this.now());
    }));
    this.registerEvent(this.app.vault.on('modify', (file) => {
      this.latestFileMtime = Math.max(this.latestFileMtime, Number(file.stat?.mtime) || this.now());
    }));
    this.registerEvent(this.app.vault.on('rename', (file) => {
      this.latestFileMtime = Math.max(this.latestFileMtime, Number(file.stat?.mtime) || this.now());
    }));
    this.registerEvent(this.app.vault.on('delete', () => {
      const currentFiles = this.app.vault.getFiles();
      this.fileCount = currentFiles.length;
      this.latestFileMtime = currentFiles.reduce((latest, file) => Math.max(latest, Number(file.stat?.mtime) || 0), 0);
    }));
  }

  onunload() {
    this.unloaded = true;
    for (const file of [this.snapshotPath, this.commandPath, this.receiptPath]) {
      if (typeof file === 'string') {
        try { fs.unlinkSync(file); } catch (_) { /* Files may already be gone. */ }
      }
    }
  }

  now() {
    return Date.now();
  }

  focusElapsed(now = this.now()) {
    const running = this.focus.state === 'running' && Number.isFinite(this.focus.startedAt)
      ? Math.max(0, now - this.focus.startedAt)
      : 0;
    const elapsedMs = Math.min(this.focus.durationSeconds * 1000, this.focus.elapsedMs + running);
    if (elapsedMs >= this.focus.durationSeconds * 1000 && this.focus.state === 'running') {
      this.focus.state = 'completed';
      this.focus.elapsedMs = this.focus.durationSeconds * 1000;
      this.focus.startedAt = null;
    }
    return this.focus.elapsedMs + (this.focus.state === 'running' ? running : 0);
  }

  startFocusTimer() {
    this.focus = { state: 'running', elapsedMs: 0, startedAt: this.now(), durationSeconds: FOCUS_DURATION_SECONDS };
    void this.publishSnapshot();
  }

  pauseFocusTimer() {
    if (this.focus.state === 'running') {
      this.focus.elapsedMs = Math.min(this.focus.durationSeconds * 1000, this.focusElapsed());
      this.focus.state = 'paused';
      this.focus.startedAt = null;
      void this.publishSnapshot();
    }
  }

  resumeFocusTimer() {
    if (this.focus.state === 'paused') {
      this.focus.state = 'running';
      this.focus.startedAt = this.now();
      void this.publishSnapshot();
    }
  }

  stopFocusTimer() {
    this.focus = { state: 'idle', elapsedMs: 0, startedAt: null, durationSeconds: FOCUS_DURATION_SECONDS };
    void this.publishSnapshot();
  }

  async processCommand() {
    if (this.processingCommand || this.unloaded) return;
    this.processingCommand = true;
    try {
      const metadata = await fs.promises.lstat(this.commandPath);
      if (!metadata.isFile() || metadata.isSymbolicLink() || metadata.size > 4096) return;
      const command = JSON.parse(await fs.promises.readFile(this.commandPath, 'utf8'));
      await fs.promises.unlink(this.commandPath);
      if (command?.kind !== COMMAND_SCHEMA || typeof command.requestId !== 'string') return;
      const actions = {
        'focus.start': () => this.startFocusTimer(),
        'focus.pause': () => this.pauseFocusTimer(),
        'focus.resume': () => this.resumeFocusTimer(),
        'focus.stop': () => this.stopFocusTimer(),
      };
      if (!Object.prototype.hasOwnProperty.call(actions, command.action)) {
        await this.writeReceipt(command.requestId, false, 'Unsupported focus action.');
        return;
      }
      actions[command.action]();
      await this.writeReceipt(command.requestId, true, null);
    } catch (error) {
      if (error?.code !== 'ENOENT') {
        new Notice('WinCraft could not read a local focus timer request.');
      }
    } finally {
      this.processingCommand = false;
    }
  }

  async writeReceipt(requestId, ok, message) {
    const value = JSON.stringify({ requestId, ok, message, writtenAt: new Date().toISOString() });
    const temporary = `${this.receiptPath}.${crypto.randomUUID()}.tmp`;
    await fs.promises.writeFile(temporary, value, { encoding: 'utf8', flag: 'wx' });
    await fs.promises.rename(temporary, this.receiptPath);
  }

  async publishSnapshot() {
    if (this.publishing || this.unloaded) return;
    this.publishing = true;
    try {
      const tabs = [];
      let paneCount = 0;
      this.app.workspace.iterateAllLeaves((leaf) => {
        paneCount += 1;
        if (tabs.length >= MAX_TABS) return;
        const title = leaf.view?.getDisplayText?.() || leaf.view?.file?.basename || '';
        if (typeof title === 'string' && title.trim()) tabs.push(title.trim().slice(0, 120));
      });
      const activeTitle = this.app.workspace.activeLeaf?.view?.getDisplayText?.()
        || this.app.workspace.activeLeaf?.view?.file?.basename || '';
      const now = this.now();
      const elapsedMs = this.focusElapsed(now);
      const snapshot = {
        kind: SNAPSHOT_SCHEMA,
        instanceId: this.instanceId,
        generatedAt: new Date(now).toISOString(),
        fileCount: this.fileCount,
        latestFileMtime: this.latestFileMtime > 0 ? new Date(this.latestFileMtime).toISOString() : null,
        workspacePaneCount: paneCount,
        activeTitle: typeof activeTitle === 'string' ? activeTitle.trim().slice(0, 120) : '',
        tabs,
        focus: {
          state: this.focus.state,
          elapsedSeconds: Math.floor(elapsedMs / 1000),
          durationSeconds: this.focus.durationSeconds,
        },
      };
      const temporary = `${this.snapshotPath}.${crypto.randomUUID()}.tmp`;
      await fs.promises.writeFile(temporary, JSON.stringify(snapshot), { encoding: 'utf8', flag: 'wx' });
      await fs.promises.rename(temporary, this.snapshotPath);
    } catch (_) {
      new Notice('WinCraft could not refresh Obsidian workspace metadata.');
    } finally {
      this.publishing = false;
    }
  }
}

module.exports = WinCraftWorkspaceDashboard;
