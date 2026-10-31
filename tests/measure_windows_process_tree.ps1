#requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateRange(1, 2147483647)]
    [int]$RootProcessId,

    [ValidateRange(5, 3600)]
    [int]$DurationSeconds = 60,

    [ValidateRange(250, 5000)]
    [int]$SampleIntervalMilliseconds = 1000
)

$ErrorActionPreference = 'Stop'
$LogicalProcessors = [Math]::Max(1, [Environment]::ProcessorCount)
$CpuTicksByProcess = @{}
$Samples = [System.Collections.Generic.List[object]]::new()

function Get-ProcessTreeSnapshot {
    param([int]$ProcessId)

    $processes = @(Get-CimInstance Win32_Process -Property @(
        'ProcessId', 'ParentProcessId', 'Name', 'CreationDate',
        'WorkingSetSize', 'PrivatePageCount', 'HandleCount', 'ThreadCount',
        'UserModeTime', 'KernelModeTime'
    ))
    $root = $processes | Where-Object { [int]$_.ProcessId -eq $ProcessId } | Select-Object -First 1
    if ($null -eq $root) {
        return $null
    }

    $childrenByParent = @{}
    foreach ($process in $processes) {
        $parentId = [int]$process.ParentProcessId
        if (-not $childrenByParent.ContainsKey($parentId)) {
            $childrenByParent[$parentId] = [System.Collections.Generic.List[object]]::new()
        }
        $childrenByParent[$parentId].Add($process)
    }

    $queue = [System.Collections.Generic.Queue[object]]::new()
    $queue.Enqueue($root)
    $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
    $tree = [System.Collections.Generic.List[object]]::new()
    while ($queue.Count -gt 0) {
        $process = $queue.Dequeue()
        $key = '{0}|{1}' -f [int]$process.ProcessId, [string]$process.CreationDate
        if (-not $seen.Add($key)) {
            continue
        }
        $tree.Add($process)
        $childKey = [int]$process.ProcessId
        if ($childrenByParent.ContainsKey($childKey)) {
            foreach ($child in $childrenByParent[$childKey]) {
                $queue.Enqueue($child)
            }
        }
    }

    $nameCounts = @{}
    [long]$workingSet = 0
    [long]$privateBytes = 0
    [long]$handles = 0
    [long]$threads = 0
    [double]$cpuTicks = 0
    foreach ($process in $tree) {
        $name = [string]$process.Name
        if (-not $nameCounts.ContainsKey($name)) {
            $nameCounts[$name] = 0
        }
        $nameCounts[$name]++
        $workingSet += [long]$process.WorkingSetSize
        $privateBytes += [long]$process.PrivatePageCount
        if ($null -ne $process.HandleCount) { $handles += [long]$process.HandleCount }
        if ($null -ne $process.ThreadCount) { $threads += [long]$process.ThreadCount }
        $processKey = '{0}|{1}' -f [int]$process.ProcessId, [string]$process.CreationDate
        $currentTicks = [double]$process.UserModeTime + [double]$process.KernelModeTime
        if (-not $CpuTicksByProcess.ContainsKey($processKey) -or $currentTicks -gt $CpuTicksByProcess[$processKey]) {
            $CpuTicksByProcess[$processKey] = $currentTicks
        }
    }
    foreach ($ticks in $CpuTicksByProcess.Values) {
        $cpuTicks += [double]$ticks
    }

    [pscustomobject]@{
        root_process_name = [string]$root.Name
        process_count = $tree.Count
        process_names = $nameCounts
        working_set_bytes = $workingSet
        private_bytes = $privateBytes
        handles = $handles
        threads = $threads
        cumulative_cpu_100ns = $cpuTicks
    }
}

function Get-Percentile {
    param([double[]]$Values, [double]$Percentile)
    if ($Values.Count -eq 0) { return $null }
    $ordered = @($Values | Sort-Object)
    $index = [Math]::Max(0, [Math]::Ceiling($Percentile * $ordered.Count) - 1)
    return [double]$ordered[$index]
}

function Get-PowerContext {
    $schemeName = 'unknown'
    try {
        $schemeText = (& powercfg /getactivescheme 2>$null | Out-String).Trim()
        $match = [regex]::Match($schemeText, '\((?<name>[^()]*)\)\s*$')
        if ($match.Success) {
            $schemeName = $match.Groups['name'].Value
        }
    } catch { }

    $batteryCount = $null
    try { $batteryCount = @(Get-CimInstance Win32_Battery -ErrorAction Stop).Count } catch { }
    $acpiSourceCount = $null
    try {
        $acpiSourceCount = @(
            Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_PowerSource -ErrorAction Stop
        ).Count
    } catch { }

    [pscustomobject]@{
        active_power_scheme = $schemeName
        battery_device_count = $batteryCount
        acpi_power_source_device_count = $acpiSourceCount
    }
}

$PowerContextBefore = Get-PowerContext
$Timer = [System.Diagnostics.Stopwatch]::StartNew()
$PreviousCpuTicks = $null
$PreviousSampleSeconds = $null

while ($Timer.Elapsed.TotalSeconds -lt $DurationSeconds) {
    $snapshot = Get-ProcessTreeSnapshot -ProcessId $RootProcessId
    if ($null -eq $snapshot) {
        throw "Root process $RootProcessId exited before the measurement ended."
    }
    $now = $Timer.Elapsed.TotalSeconds
    $cpuPercent = $null
    $cpuOneCorePercent = $null
    if ($null -ne $PreviousCpuTicks -and $null -ne $PreviousSampleSeconds) {
        $elapsed = $now - $PreviousSampleSeconds
        if ($elapsed -gt 0) {
            $deltaTicks = [Math]::Max(0, $snapshot.cumulative_cpu_100ns - $PreviousCpuTicks)
            $cpuOneCorePercent = $deltaTicks / ($elapsed * 10000000.0) * 100.0
            $cpuPercent = $cpuOneCorePercent / $LogicalProcessors
        }
    }
    $Samples.Add([pscustomobject]@{
        elapsed_seconds = [Math]::Round($now, 3)
        root_process_name = $snapshot.root_process_name
        process_count = $snapshot.process_count
        process_names = $snapshot.process_names
        working_set_bytes = $snapshot.working_set_bytes
        private_bytes = $snapshot.private_bytes
        handles = $snapshot.handles
        threads = $snapshot.threads
        cpu_machine_percent = if ($null -eq $cpuPercent) { $null } else { [Math]::Round($cpuPercent, 3) }
        cpu_one_core_percent = if ($null -eq $cpuOneCorePercent) { $null } else { [Math]::Round($cpuOneCorePercent, 3) }
    })
    $PreviousCpuTicks = $snapshot.cumulative_cpu_100ns
    $PreviousSampleSeconds = $now
    Start-Sleep -Milliseconds $SampleIntervalMilliseconds
}

$Timer.Stop()
$PowerContextAfter = Get-PowerContext
$cpuMachine = @($Samples | Where-Object { $null -ne $_.cpu_machine_percent } | ForEach-Object { [double]$_.cpu_machine_percent })
$workingSets = @($Samples | ForEach-Object { [double]$_.working_set_bytes })
$privateSets = @($Samples | ForEach-Object { [double]$_.private_bytes })
$handleCounts = @($Samples | ForEach-Object { [double]$_.handles })
$processCounts = @($Samples | ForEach-Object { [double]$_.process_count })
$sampleIntervals = @()
for ($index = 1; $index -lt $Samples.Count; $index++) {
    $sampleIntervals += [double]$Samples[$index].elapsed_seconds - [double]$Samples[$index - 1].elapsed_seconds
}
$summary = [ordered]@{
    schema = 'wincraft.windows-process-tree-measurement.v1'
    measurement_seconds = [Math]::Round($Timer.Elapsed.TotalSeconds, 3)
    sample_interval_milliseconds = $SampleIntervalMilliseconds
    sample_count = $Samples.Count
    median_sample_interval_seconds = Get-Percentile -Values $sampleIntervals -Percentile 0.5
    p95_sample_interval_seconds = Get-Percentile -Values $sampleIntervals -Percentile 0.95
    logical_processors = $LogicalProcessors
    root_process_name = $Samples[0].root_process_name
    peak_process_count = [long](($processCounts | Measure-Object -Maximum).Maximum)
    peak_working_set_bytes = [long](($workingSets | Measure-Object -Maximum).Maximum)
    peak_private_bytes = [long](($privateSets | Measure-Object -Maximum).Maximum)
    peak_handles = [long](($handleCounts | Measure-Object -Maximum).Maximum)
    p95_cpu_machine_percent = Get-Percentile -Values $cpuMachine -Percentile 0.95
    p95_cpu_one_core_percent = Get-Percentile -Values @($Samples | Where-Object { $null -ne $_.cpu_one_core_percent } | ForEach-Object { [double]$_.cpu_one_core_percent }) -Percentile 0.95
    power_context = @{
        before = $PowerContextBefore
        after = $PowerContextAfter
        sleep_wake_transition_injected = $false
        sleep_wake_behavior_verified = $false
    }
    process_names_seen = @($Samples | ForEach-Object { $_.process_names.Keys } | Sort-Object -Unique)
    samples = @($Samples)
}
$summary | ConvertTo-Json -Depth 8
