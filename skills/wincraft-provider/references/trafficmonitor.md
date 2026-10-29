# TrafficMonitor provider reference

This adapter is plugin-backed. TrafficMonitor remains the source of the selected
readings; WinCraft stores only a rebuildable component tree and rendered values.
The bridge DLL consumes TrafficMonitor's `ITMPlugin::OnMonitorInfo` callback, then
atomically publishes a small local JSON snapshot. The Python provider validates that
snapshot and sends declarative scene/data messages over the normal WinCraft protocol.

## Build and stage a separate copy

Build output and the staged application must be outside the original TrafficMonitor
directory. Use new, empty temporary directories because the build and staging scripts
refuse to overwrite previous output:

```powershell
$pluginOutput = 'E:\tmp\wincraft-tm-build-<unique>'
$stageDirectory = 'E:\tmp\wincraft-tm-stage-<unique>'
$trafficMonitorDirectory = '<the extracted TrafficMonitor package directory>'

.\examples\trafficmonitor\build_bridge.ps1 -OutputDirectory $pluginOutput
.\examples\trafficmonitor\stage_demo.ps1 `
  -TrafficMonitorDirectory $trafficMonitorDirectory `
  -PluginDll (Join-Path $pluginOutput 'wincraft_trafficmonitor_bridge.dll') `
  -WorkDirectory $stageDirectory `
  -EnableBridgeItem
```

For this fresh package, do not use `-ReuseConfiguration`. When `-EnableBridgeItem`
finds no staged `config.ini`, it creates a temporary config that enables the
taskbar window, leaves plugins enabled, and selects the WinCraft item in the
`[task_bar]` section. TrafficMonitor supplies its other defaults.
`-ReuseConfiguration` remains available for a future explicitly configured run and
copies `config.ini` and `global_cfg.ini` from the package directory when present.
Package language/skin/logo assets are copied into the new temporary directory only.
The source package is not modified, and no other plugins are copied. The staging
script checks for an already-running `TrafficMonitor.exe`; when one is present, it
leaves the staged copy inert and reports `blocked-existing-process`. Close the
existing instance manually before considering a staged run.

`-EnableBridgeItem` changes only the marked staged copy. If no `config.ini` exists,
the helper creates a temporary file with `[config] show_task_bar_wnd=true`, an empty
`plugin_disabled` list, and `[task_bar] plugin_display_item=wincraft.bridge`.
Otherwise it modifies only an empty plugin selection and preserves the other bytes.
If the setting already contains another plugin selection, the helper refuses to
overwrite it; enable the WinCraft item in the staged app's UI instead.

`OpenHardwareMonitorApi.dll` and `LibreHardwareMonitorLib.dll` are optional; the
script copies them only when present. `TrafficMonitor.sys` is deliberately never
staged: the WinCraft bridge consumes ordinary plugin callbacks and does not require
a kernel driver. The verified V1.86 x64 Lite archive contains none of these optional
files. The script never requests elevation. Missing hardware readings remain
unavailable rather than prompting a driver install. Do not use the original
installation as the test target.

## Start the provider

First start the intended local WinCraft host and copy its actual runtime descriptor
path from the manager. Never guess a port or enumerate descriptor files. Then run:

```powershell
$runtimePath = '<the exact descriptor path shown by this host manager>'
$metricsPath = Join-Path $stageDirectory 'trafficmonitor-metrics.json'
python .\examples\python\trafficmonitor_provider.py `
  --runtime $runtimePath `
  --metrics $metricsPath `
  --verbose
```

The bridge writes only the selected download, upload, CPU, memory, GPU, version,
timestamp, and generation fields. The provider creates an invite-only world and
updates it using the regular window-level lease and `data.replace` protocol. It does
not send metrics to a remote service or accept arbitrary code. `--verbose` reports
source status, sample age, generation, version, and accepted revision without metric
values. Keep the descriptor path and snapshot contents out of logs and screenshots.

## Verify source freshness

- The staged plugin also writes `trafficmonitor-bridge-status.json` with API-pointer,
  API-version, `DataRequired`/`OnMonitorInfo` counts, generation, and write-status
  fields only. It contains no monitor readings and helps distinguish a missing output
  path from an inactive plugin.
- In V1.86, the verified source path is `OnMonitorInfo(MonitorInfo)`. A false
  `api_pointer_available` flag is not itself a feed failure when
  `monitor_info_calls` and generation advance and `last_sample_write_ok` is true.
- If `output_path_configured` is false, fix the stage environment/launcher. If no
  `OnMonitorInfo` calls arrive, keep the provider waiting and inspect plugin load and
  item selection; do not substitute synthetic readings.
- Confirm the staged TrafficMonitor copy loaded the bridge plugin. The local snapshot
  must appear and its `generation` and `sampled_at_ms` must advance.
- The WinCraft view reports online only while the latest sample is within five
  seconds. Missing, invalid, and stale snapshots remain visible as source states;
  missing readings are shown as unavailable, not as numeric zero.
- If no snapshot appears, leave the view in its waiting state and inspect plugin load
  and the configured output path in the staged copy. Do not claim a live integration
  from the Python parser tests or DLL build alone.
- Stop the Python provider with Ctrl+C so it can destroy its temporary world, then
  close the staged TrafficMonitor copy. Leave the original installation untouched.

The provider unit tests use synthetic fixture files and are parser/state tests only.
Only an advancing snapshot written by the loaded TrafficMonitor plugin proves the
real source-to-provider path.

## Migrate a configured install after the fresh test

Do not replace the existing installation as part of the fresh x64 integration test.
For a later architecture upgrade on 64-bit Windows, use the author's [V1.86 release
page](https://gitee.com/zhongyang219/TrafficMonitor/releases) and choose the x64
package. First close the old instance and make a private backup of
`config.ini`, `global_cfg.ini`, and any custom `skins`, `language`, or `Logo` assets.
Extract the official x64 package beside the old installation, verify its EXE
architecture and release hash, then copy only the settings/assets you intend to keep
into a temporary package copy. Run `stage_demo.ps1 -ReuseConfiguration` against that
copy and confirm its bridge snapshot advances before changing shortcuts or startup
tasks. Never copy `TrafficMonitor.sys` or change the original startup entry just to
make the provider demo pass; keep the old directory available for rollback until the
user confirms the upgrade.
