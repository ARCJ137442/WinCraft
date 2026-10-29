param(
    [Parameter(Mandatory = $true)]
    [string]$TrafficMonitorDirectory,
    [Parameter(Mandatory = $true)]
    [string]$PluginDll,
    [Parameter(Mandatory = $true)]
    [string]$WorkDirectory,
    [switch]$ReuseConfiguration,
    [switch]$EnableBridgeItem
)

$ErrorActionPreference = 'Stop'
$elevationRequiredErrorCode = 740

function Get-PeArchitecture {
    param([Parameter(Mandatory = $true)][string]$Path)

    $stream = [System.IO.File]::OpenRead($Path)
    $reader = [System.IO.BinaryReader]::new($stream)
    try {
        if ($reader.ReadUInt16() -ne 0x5a4d) {
            throw "Not a PE executable: $Path"
        }
        $stream.Position = 0x3c
        $peOffset = $reader.ReadInt32()
        if ($peOffset -lt 0 -or $peOffset -gt ($stream.Length - 6)) {
            throw "Invalid PE header offset: $Path"
        }
        $stream.Position = $peOffset
        if ($reader.ReadUInt32() -ne 0x00004550) {
            throw "Invalid PE signature: $Path"
        }
        $machine = $reader.ReadUInt16()
        switch ($machine) {
            0x014c { return 'x86' }
            0x8664 { return 'x64' }
            default { throw "Unsupported PE machine 0x$($machine.ToString('x4')): $Path" }
        }
    } finally {
        $reader.Dispose()
    }
}

$sourceRoot = (Resolve-Path -LiteralPath $TrafficMonitorDirectory).Path
$sourceRoot = [System.IO.Path]::GetFullPath($sourceRoot).TrimEnd('\')
$workRoot = [System.IO.Path]::GetFullPath($WorkDirectory).TrimEnd('\')
$pluginPath = (Resolve-Path -LiteralPath $PluginDll).Path
if ($workRoot.StartsWith($sourceRoot + '\', [System.StringComparison]::OrdinalIgnoreCase) -or $workRoot -eq $sourceRoot) {
    throw 'WorkDirectory must be outside the source TrafficMonitor folder.'
}
if (Test-Path -LiteralPath $workRoot) {
    throw "Refusing to reuse an existing test directory: $workRoot"
}

$requiredFiles = @(
    'TrafficMonitor.exe'
)
foreach ($name in $requiredFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot $name) -PathType Leaf)) {
        throw "TrafficMonitor source is missing required file: $name"
    }
}
$trafficMonitorArchitecture = Get-PeArchitecture -Path (Join-Path $sourceRoot 'TrafficMonitor.exe')
$bridgeArchitecture = Get-PeArchitecture -Path $pluginPath
if ($trafficMonitorArchitecture -ne $bridgeArchitecture) {
    throw "Architecture mismatch: TrafficMonitor is $trafficMonitorArchitecture but the bridge DLL is $bridgeArchitecture. Build the bridge with -Architecture $trafficMonitorArchitecture."
}

New-Item -ItemType Directory -Path $workRoot | Out-Null
foreach ($name in $requiredFiles) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot $name) -Destination $workRoot
}
$copiedOptionalFiles = @()
# The WinCraft bridge consumes TrafficMonitor's plugin callbacks; the demo never stages a kernel driver.
foreach ($name in @('OpenHardwareMonitorApi.dll', 'LibreHardwareMonitorLib.dll')) {
    $sourceFile = Join-Path $sourceRoot $name
    if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
        Copy-Item -LiteralPath $sourceFile -Destination $workRoot
        $copiedOptionalFiles += $name
    }
}
$copiedConfigurationFiles = @()
if ($ReuseConfiguration) {
    foreach ($name in @('config.ini', 'global_cfg.ini')) {
        $sourceFile = Join-Path $sourceRoot $name
        if (Test-Path -LiteralPath $sourceFile -PathType Leaf) {
            Copy-Item -LiteralPath $sourceFile -Destination $workRoot
            $copiedConfigurationFiles += $name
        }
    }
}
foreach ($folder in @('language', 'skins', 'Logo')) {
    $sourceFolder = Join-Path $sourceRoot $folder
    if (Test-Path -LiteralPath $sourceFolder -PathType Container) {
        Copy-Item -LiteralPath $sourceFolder -Destination $workRoot -Recurse
    }
}
$pluginFolder = Join-Path $workRoot 'plugins'
New-Item -ItemType Directory -Path $pluginFolder | Out-Null
Copy-Item -LiteralPath $pluginPath -Destination (Join-Path $pluginFolder 'wincraft_trafficmonitor_bridge.dll')
[System.IO.File]::WriteAllText(
    (Join-Path $workRoot '.wincraft-trafficmonitor-stage'),
    "wincraft-trafficmonitor-stage-v1`n",
    [System.Text.Encoding]::ASCII
)

$bridgeItemStatus = 'not-requested'
if ($EnableBridgeItem) {
    $configurator = Join-Path $PSScriptRoot 'configure_staged_copy.py'
    if (-not (Test-Path -LiteralPath $configurator -PathType Leaf)) {
        throw 'The staged-copy config helper is missing.'
    }
    $configArguments = @('--stage-directory', $workRoot)
    if (-not $ReuseConfiguration) {
        $configArguments += '--create-config-if-missing'
    }
    $configResult = & python $configurator @configArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Could not enable the WinCraft bridge item in the staged config (exit $LASTEXITCODE)."
    }
    $bridgeItemStatus = ($configResult | ConvertFrom-Json).status
}

$metricsPath = Join-Path $workRoot 'trafficmonitor-metrics.json'
$statusPath = Join-Path $workRoot 'trafficmonitor-bridge-status.json'
$versionInfo = [System.Diagnostics.FileVersionInfo]::GetVersionInfo(
    (Join-Path $workRoot 'TrafficMonitor.exe')
)
$trafficMonitorVersion = if (-not [string]::IsNullOrWhiteSpace($versionInfo.FileVersion)) {
    $versionInfo.FileVersion
} else {
    $versionInfo.ProductVersion
}
$manualLauncherPath = Join-Path $workRoot 'run_staged.cmd'
$manualLauncher = @"
@echo off
setlocal
set "WINCRAFT_TRAFFICMONITOR_OUT=%~dp0trafficmonitor-metrics.json"
set "WINCRAFT_TRAFFICMONITOR_STATUS=%~dp0trafficmonitor-bridge-status.json"
set "WINCRAFT_TRAFFICMONITOR_VERSION=$trafficMonitorVersion"
pushd "%~dp0"
"%~dp0TrafficMonitor.exe"
set "trafficmonitor_exit=%ERRORLEVEL%"
popd
exit /b %trafficmonitor_exit%
"@
[System.IO.File]::WriteAllText($manualLauncherPath, $manualLauncher, [System.Text.Encoding]::ASCII)

# A live user instance may receive a single-instance launch or share settings.
# Keep the staged copy inert until the existing process has been closed manually.
try {
    $existingInstances = @(Get-CimInstance Win32_Process -Filter "Name = 'TrafficMonitor.exe'" -ErrorAction Stop)
} catch {
    [pscustomobject]@{
        ProcessId = $null
        Executable = Join-Path $workRoot 'TrafficMonitor.exe'
        MetricsPath = $metricsPath
        StatusPath = $statusPath
        ManualLauncher = $manualLauncherPath
        ReusedConfiguration = $ReuseConfiguration.IsPresent
        CopiedConfigurationFiles = $copiedConfigurationFiles
        CopiedOptionalFiles = $copiedOptionalFiles
        BridgeItemStatus = $bridgeItemStatus
        Architecture = $trafficMonitorArchitecture
        TrafficMonitorVersion = $trafficMonitorVersion
        LaunchStatus = 'blocked-process-check'
        Note = 'Could not verify whether another TrafficMonitor instance is running; the staged copy was not launched.'
    } | ConvertTo-Json -Compress
    return
}
if ($existingInstances.Count -gt 0) {
    [pscustomobject]@{
        ProcessId = $null
        Executable = Join-Path $workRoot 'TrafficMonitor.exe'
        MetricsPath = $metricsPath
        StatusPath = $statusPath
        ManualLauncher = $manualLauncherPath
        ReusedConfiguration = $ReuseConfiguration.IsPresent
        CopiedConfigurationFiles = $copiedConfigurationFiles
        CopiedOptionalFiles = $copiedOptionalFiles
        BridgeItemStatus = $bridgeItemStatus
        Architecture = $trafficMonitorArchitecture
        TrafficMonitorVersion = $trafficMonitorVersion
        LaunchStatus = 'blocked-existing-process'
        Note = 'Check CopiedOptionalFiles before an elevated launch; any bundled driver needs explicit review.'
    } | ConvertTo-Json -Compress
    return
}

$startInfo = [System.Diagnostics.ProcessStartInfo]::new()
$startInfo.FileName = Join-Path $workRoot 'TrafficMonitor.exe'
$startInfo.WorkingDirectory = $workRoot
$startInfo.UseShellExecute = $false
$metricsEnvironmentName = 'WINCRAFT_TRAFFICMONITOR_OUT'
$statusEnvironmentName = 'WINCRAFT_TRAFFICMONITOR_STATUS'
$versionEnvironmentName = 'WINCRAFT_TRAFFICMONITOR_VERSION'
$previousMetricsEnvironment = [Environment]::GetEnvironmentVariable($metricsEnvironmentName, 'Process')
$previousStatusEnvironment = [Environment]::GetEnvironmentVariable($statusEnvironmentName, 'Process')
$previousVersionEnvironment = [Environment]::GetEnvironmentVariable($versionEnvironmentName, 'Process')
[Environment]::SetEnvironmentVariable($metricsEnvironmentName, $metricsPath, 'Process')
[Environment]::SetEnvironmentVariable($statusEnvironmentName, $statusPath, 'Process')
[Environment]::SetEnvironmentVariable($versionEnvironmentName, $trafficMonitorVersion, 'Process')
try {
    $process = [System.Diagnostics.Process]::Start($startInfo)
} catch {
    $nativeErrorCode = $null
    $startException = $_.Exception
    while ($null -ne $startException) {
        if ($startException -is [System.ComponentModel.Win32Exception]) {
            $nativeErrorCode = $startException.NativeErrorCode
            break
        }
        $startException = $startException.InnerException
    }

    if ($nativeErrorCode -ne $elevationRequiredErrorCode) {
        throw
    }

    [pscustomobject]@{
        ProcessId = $null
        Executable = $startInfo.FileName
        MetricsPath = $metricsPath
        StatusPath = $statusPath
        ManualLauncher = $manualLauncherPath
        ReusedConfiguration = $ReuseConfiguration.IsPresent
        CopiedConfigurationFiles = $copiedConfigurationFiles
        CopiedOptionalFiles = $copiedOptionalFiles
        BridgeItemStatus = $bridgeItemStatus
        Architecture = $trafficMonitorArchitecture
        TrafficMonitorVersion = $trafficMonitorVersion
        LaunchStatus = 'manual-elevation-required'
        Note = 'No elevation was requested by this script. Check CopiedOptionalFiles and review system effects before any manual elevated launch.'
    } | ConvertTo-Json -Compress
    return
} finally {
    [Environment]::SetEnvironmentVariable($metricsEnvironmentName, $previousMetricsEnvironment, 'Process')
    [Environment]::SetEnvironmentVariable($statusEnvironmentName, $previousStatusEnvironment, 'Process')
    [Environment]::SetEnvironmentVariable($versionEnvironmentName, $previousVersionEnvironment, 'Process')
}
if ($null -eq $process) {
    throw 'Windows did not start the staged TrafficMonitor copy.'
}

Start-Sleep -Seconds 2
$process.Refresh()
if ($process.HasExited) {
    throw 'The staged copy did not remain as a separate process. The existing installation was not changed.'
}
$runningPath = $process.MainModule.FileName
if (-not $runningPath.StartsWith($workRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'The process did not originate from the staged copy. The existing installation was not changed.'
}

[pscustomobject]@{
    ProcessId = $process.Id
    Executable = Join-Path $workRoot 'TrafficMonitor.exe'
    MetricsPath = $metricsPath
    StatusPath = $statusPath
    ManualLauncher = $manualLauncherPath
    ReusedConfiguration = $ReuseConfiguration.IsPresent
    CopiedConfigurationFiles = $copiedConfigurationFiles
    CopiedOptionalFiles = $copiedOptionalFiles
    BridgeItemStatus = $bridgeItemStatus
    Architecture = $trafficMonitorArchitecture
    TrafficMonitorVersion = $trafficMonitorVersion
    LaunchStatus = 'running'
    Note = 'Temporary copy only; close this PID and remove WorkDirectory after testing.'
} | ConvertTo-Json -Compress
