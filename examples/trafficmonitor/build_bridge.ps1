param(
    [Parameter(Mandatory = $true)]
    [string]$OutputDirectory,
    [ValidateSet('x86', 'x64')]
    [string]$Architecture = 'x64'
)

$ErrorActionPreference = 'Stop'

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path -LiteralPath $vswhere)) {
    throw 'Visual Studio Build Tools with the C++ workload is required.'
}
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath | Select-Object -First 1
if (-not $installation) {
    throw 'Could not locate Visual Studio C++ Build Tools.'
}
$vcvarsAll = Join-Path $installation 'VC\Auxiliary\Build\vcvarsall.bat'
if (-not (Test-Path -LiteralPath $vcvarsAll)) {
    throw 'The Visual Studio vcvarsall.bat script is missing.'
}
$targetArchitecture = if ($Architecture -eq 'x86') { 'amd64_x86' } else { 'amd64' }
$environmentLines = & $env:ComSpec /d /s /c "call `"$vcvarsAll`" $targetArchitecture >nul && set"
if ($LASTEXITCODE -ne 0) {
    throw "vcvarsall.bat failed to configure $Architecture (exit $LASTEXITCODE)"
}
foreach ($line in $environmentLines) {
    $separator = $line.IndexOf('=')
    if ($separator -gt 0) {
        $name = $line.Substring(0, $separator)
        $value = $line.Substring($separator + 1)
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}
if ([string]::IsNullOrWhiteSpace($env:INCLUDE)) {
    throw 'Visual Studio did not provide C++ include paths.'
}

$outputPath = [System.IO.Path]::GetFullPath($OutputDirectory)
if (-not (Test-Path -LiteralPath $outputPath -PathType Container)) {
    New-Item -ItemType Directory -Path $outputPath | Out-Null
}
$dllPath = Join-Path $outputPath 'wincraft_trafficmonitor_bridge.dll'
if (Test-Path -LiteralPath $dllPath) {
    throw "Refusing to overwrite existing build output: $dllPath"
}

$sourcePath = Join-Path $PSScriptRoot 'wincraft_bridge.cpp'
$compiler = Get-Command cl.exe -ErrorAction Stop
$machine = if ($Architecture -eq 'x86') { 'X86' } else { 'X64' }
$arguments = @(
    '/nologo', '/LD', '/std:c++17', '/EHsc', '/W4', '/external:W0',
    "/external:I$(Join-Path $PSScriptRoot 'vendor')", "/Fo$outputPath\", $sourcePath,
    '/link', "/MACHINE:$machine", "/OUT:$dllPath",
    "/IMPLIB:$(Join-Path $outputPath 'wincraft_trafficmonitor_bridge.lib')"
)
& $compiler.Source @arguments
if ($LASTEXITCODE -ne 0) {
    throw "cl.exe failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $dllPath -PathType Leaf)) {
    throw 'Compiler returned success without creating the expected DLL.'
}

Get-Item -LiteralPath $dllPath | Select-Object FullName, Length, LastWriteTime,
    @{Name = 'Architecture'; Expression = { $Architecture }}
