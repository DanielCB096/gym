[CmdletBinding()]
param(
    [string]$BackupRoot,
    [ValidateRange(1,365)]
    [int]$RetentionCount = 14
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env.staging.local"
$ComposeFile = Join-Path $Root "compose.staging.local.yml"
if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
    $BackupRoot = Join-Path $Root "backups\local-staging"
}

if (-not (Test-Path $EnvFile)) {
    throw "No existe $EnvFile. Ejecuta demo/start-local-staging.ps1 primero."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop no está disponible en PATH."
}

$composeArgs = @("compose", "--env-file", $EnvFile, "-f", $ComposeFile)
$dbContainer = (& docker @composeArgs ps -q db).Trim()
$apiContainer = (& docker @composeArgs ps -q api).Trim()
if (-not $dbContainer -or -not $apiContainer) {
    throw "Staging detenido. Inicia el entorno antes de crear el respaldo."
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$backupDir = Join-Path $BackupRoot $timestamp
[void](New-Item -ItemType Directory -Path $backupDir -Force)

$dumpName = "database.dump"
$uploadsName = "uploads.tar.gz"
$dumpPath = Join-Path $backupDir $dumpName
$uploadsPath = Join-Path $backupDir $uploadsName
$startedAt = (Get-Date).ToUniversalTime()

try {
    & docker @composeArgs exec -T db pg_dump `
        --format=custom `
        --no-owner `
        --no-privileges `
        --file="/tmp/gym-staging.dump" `
        --username=gym_staging `
        gym_staging
    if ($LASTEXITCODE -ne 0) { throw "pg_dump terminó con un error." }

    & docker cp "${dbContainer}:/tmp/gym-staging.dump" $dumpPath
    if ($LASTEXITCODE -ne 0) { throw "No se pudo copiar el dump desde el contenedor." }
    & docker @composeArgs exec -T db rm -f /tmp/gym-staging.dump

    & docker run --rm `
        --volumes-from $apiContainer `
        -v "${backupDir}:/backup" `
        alpine:3.20 `
        sh -c "mkdir -p /tmp/uploads-empty; tar -czf /backup/uploads.tar.gz -C /app/uploads ."
    if ($LASTEXITCODE -ne 0) { throw "No se pudo empaquetar el volumen de fotos." }

    if (-not (Test-Path $dumpPath) -or (Get-Item $dumpPath).Length -eq 0) {
        throw "El respaldo de PostgreSQL está vacío."
    }
    if (-not (Test-Path $uploadsPath) -or (Get-Item $uploadsPath).Length -eq 0) {
        throw "El respaldo de archivos está vacío."
    }

    $finishedAt = (Get-Date).ToUniversalTime()
    $manifest = @{
        created_at_utc = $startedAt.ToString("o")
        finished_at_utc = $finishedAt.ToString("o")
        duration_seconds = [math]::Round(($finishedAt - $startedAt).TotalSeconds, 3)
        project = "gym-local-staging"
        database = "gym_staging"
        rpo_objective_seconds = 900
        synthetic_data_only = $true
        files = @(
            @{
                name = $dumpName
                sha256 = (Get-FileHash -Algorithm SHA256 $dumpPath).Hash.ToLowerInvariant()
                bytes = (Get-Item $dumpPath).Length
            },
            @{
                name = $uploadsName
                sha256 = (Get-FileHash -Algorithm SHA256 $uploadsPath).Hash.ToLowerInvariant()
                bytes = (Get-Item $uploadsPath).Length
            }
        )
    }
    $manifestPath = Join-Path $backupDir "manifest.json"
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $manifestPath
} catch {
    if (Test-Path $backupDir) {
        Remove-Item -LiteralPath $backupDir -Recurse -Force
    }
    throw
}

$directories = Get-ChildItem -LiteralPath $BackupRoot -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending
if ($directories.Count -gt $RetentionCount) {
    foreach ($oldDirectory in $directories | Select-Object -Skip $RetentionCount) {
        Remove-Item -LiteralPath $oldDirectory.FullName -Recurse -Force
    }
}

Write-Output $backupDir
