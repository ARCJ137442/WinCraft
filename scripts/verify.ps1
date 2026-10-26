param([switch]$Desktop)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
$destination = Join-Path $root 'evidence/local'
New-Item -ItemType Directory -Force $destination | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
Start-Transcript -Path (Join-Path $destination "verify-$stamp.log") | Out-Null
function Run-Step([string]$Program, [string[]]$Arguments) {
    Write-Host ("> " + $Program + ' ' + ($Arguments -join ' '))
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program exited with code $LASTEXITCODE" }
}
try {
    Run-Step 'node' @('--version')
    Run-Step 'python' @('--version')
    Run-Step 'cargo' @('--version')
    Run-Step 'npm' @('run','test:ui')
    Run-Step 'python' @('scripts/check_contracts.py')
    Run-Step 'cargo' @('fmt','--all','--','--check')
    Run-Step 'cargo' @('check','-p','wincraft-core','-p','wincraft-server')
    Run-Step 'cargo' @('test','-p','wincraft-core','-p','wincraft-server')
    Run-Step 'cargo' @('clippy','-p','wincraft-core','-p','wincraft-server','--all-targets','--','-D','warnings')
    if ($Desktop) { Run-Step 'cargo' @('check','-p','wincraft-desktop') }
    Write-Host 'Source checks passed. This script does NOT validate native GUI behavior or real ExoMind.'
} finally {
    Stop-Transcript | Out-Null
    Pop-Location
}
