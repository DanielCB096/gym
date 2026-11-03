[CmdletBinding()]
param(
    [ValidateRange(1,365)]
    [int]$RetentionCount = 14
)

$ErrorActionPreference = 'Stop'
$BackupScript = Join-Path $PSScriptRoot 'backup-local-staging.ps1'
$RestoreScript = Join-Path $PSScriptRoot 'restore-local-staging.ps1'

$startedAt = Get-Date
$backupDir = & $BackupScript -RetentionCount $RetentionCount
if ($LASTEXITCODE -ne 0 -or -not $backupDir) {
    throw 'No se pudo crear el respaldo de verificación.'
}

& $RestoreScript -BackupDir $backupDir
$finishedAt = Get-Date
$durationSeconds = [math]::Round(($finishedAt - $startedAt).TotalSeconds, 3)

Write-Host ''
Write-Host 'ENSAYO DE RECUPERACIÓN COMPLETO' -ForegroundColor Green
Write-Host "Respaldo: $backupDir"
Write-Host "Tiempo RTO medido: $durationSeconds segundos"
if ($durationSeconds -gt 14400) {
    Write-Warning 'El ensayo excedió el objetivo de RTO de 4 horas.'
} else {
    Write-Host 'Resultado: dentro del objetivo de RTO de 4 horas para este ensayo.' -ForegroundColor Green
}
