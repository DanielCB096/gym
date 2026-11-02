# Apaga los procesos que levanto demo/start-demo.ps1.
#
#   powershell -ExecutionPolicy Bypass -File demo\stop-demo.ps1

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$PidFile = Join-Path $Root "backend\.secrets\demo-pids.json"

if (-not (Test-Path $PidFile)) {
    Write-Host "No hay una demo registrada (falta $PidFile)." -ForegroundColor Yellow
    Write-Host "Si quedaron procesos escuchando, cierralos manualmente."
    exit 0
}

$payload = Get-Content $PidFile -Raw | ConvertFrom-Json
$names = @("mobile", "kiosk", "web", "backend")
$allProcesses = Get-CimInstance Win32_Process
$unsafeProcesses = 0

foreach ($name in $names) {
    $entry = $payload.$name
    if ($entry -is [System.Management.Automation.PSCustomObject]) {
        $processId = [int]$entry.id
        $expectedStart = [datetime]::Parse($entry.started_at).ToUniversalTime()
    } else {
        $processId = [int]$entry
        $processStartTimes = $payload.process_started_at
        $specificStart = if ($processStartTimes) { $processStartTimes.$name } else { $null }
        $expectedStart = if ($specificStart) {
            [datetime]::Parse($specificStart).ToUniversalTime()
        } else {
            [datetime]::Parse($payload.started_at).ToUniversalTime()
        }
    }
    if (-not $processId) { continue }

    $alive = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if (-not $alive) {
        Write-Host "  $name ($processId): ya estaba detenido." -ForegroundColor DarkGray
        continue
    }

    $actualStart = $alive.StartTime.ToUniversalTime()
    if ($actualStart -lt $expectedStart.AddSeconds(-5)) {
        Write-Host "  $name ($processId): PID reutilizado; no se detuvo." -ForegroundColor Yellow
        $unsafeProcesses++
        continue
    }

    $tree = New-Object System.Collections.Generic.List[int]
    $pending = New-Object System.Collections.Generic.Stack[int]
    $pending.Push($processId)
    while ($pending.Count -gt 0) {
        $currentId = $pending.Pop()
        $tree.Add($currentId)
        foreach ($child in $allProcesses | Where-Object { $_.ParentProcessId -eq $currentId }) {
            $pending.Push([int]$child.ProcessId)
        }
    }
    for ($index = $tree.Count - 1; $index -ge 0; $index--) {
        Stop-Process -Id $tree[$index] -Force -ErrorAction SilentlyContinue
    }
    Write-Host "  $name ($processId): detenido." -ForegroundColor Green
}

if ($unsafeProcesses -gt 0) {
    Write-Error "No se borro el registro de procesos porque hay PID reutilizados; revisa backend\.secrets\demo-pids.json antes de reintentar."
    exit 1
}

Remove-Item $PidFile -Force
Write-Host "Demo apagada. La base de demo se conserva en backend\.demo_runtime\." -ForegroundColor Green
