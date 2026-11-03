[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$BackupDir,
    [switch]$Apply
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env.staging.local"
$ComposeFile = Join-Path $Root "compose.staging.local.yml"
$BackupDir = (Resolve-Path $BackupDir).Path

$manifestPath = Join-Path $BackupDir "manifest.json"
$dumpPath = Join-Path $BackupDir "database.dump"
$uploadsPath = Join-Path $BackupDir "uploads.tar.gz"
foreach ($required in @($manifestPath, $dumpPath, $uploadsPath)) {
    if (-not (Test-Path $required)) {
        throw "Falta un archivo obligatorio del respaldo: $required"
    }
}

$manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
foreach ($file in $manifest.files) {
    $actualPath = Join-Path $BackupDir $file.name
    $actualHash = (Get-FileHash -Algorithm SHA256 $actualPath).Hash.ToLowerInvariant()
    if ($actualHash -ne $file.sha256.ToLowerInvariant()) {
        throw "SHA-256 inválido para $($file.name). La copia puede estar dañada."
    }
}

if (-not $Apply) {
    $startedAt = (Get-Date).ToUniversalTime()
    $volumeName = "gym_restore_db_$((Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss'))"
    $containerName = "gym_restore_$((Get-Date).ToUniversalTime().ToString('yyyyMMddHHmmss'))"
    $uploadVolume = "${volumeName}_uploads"
    & docker volume create $volumeName | Out-Null
    & docker volume create $uploadVolume | Out-Null

    try {
        & docker run -d --name $containerName `
            -e POSTGRES_DB=gym_restore `
            -e POSTGRES_USER=postgres `
            -e POSTGRES_PASSWORD=gym_restore_only `
            -v "${volumeName}:/var/lib/postgresql/data" `
            postgres:16-alpine | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear PostgreSQL aislado." }

        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            & docker exec $containerName pg_isready -U postgres -d gym_restore | Out-Null
            if ($LASTEXITCODE -eq 0) { $ready = $true; break }
            Start-Sleep -Seconds 1
        }
        if (-not $ready) { throw "PostgreSQL aislado no quedó disponible." }

        & docker cp $dumpPath "${containerName}:/tmp/database.dump"
        if ($LASTEXITCODE -ne 0) { throw "No se pudo copiar el dump al entorno aislado." }
        & docker exec $containerName pg_restore `
            --verbose `
            --no-owner `
            --no-privileges `
            --dbname=gym_restore `
            --username=postgres `
            /tmp/database.dump
        if ($LASTEXITCODE -ne 0) { throw "pg_restore falló en el entorno aislado." }

        $dumpInfo = & docker exec $containerName psql `
            --username=postgres `
            --dbname=gym_restore `
            --tuples-only `
            --no-align `
            --command="SELECT count(*) FROM alembic_version;"
        if ($LASTEXITCODE -ne 0) { throw "No se pudo leer la versión migrada restaurada." }

        $absoluteUploads = (Resolve-Path $uploadsPath).Path.Replace("\", "/")
        $archiveDir = Split-Path -Parent $absoluteUploads
        & docker run --rm `
            -v "${uploadVolume}:/app/uploads" `
            -v "${archiveDir}:/backup:ro" `
            alpine:3.20 `
            sh -c "mkdir -p /app/uploads && tar -xzf /backup/uploads.tar.gz -C /app/uploads"
        if ($LASTEXITCODE -ne 0) { throw "No se pudo restaurar el archivo aislado de fotos." }

        & docker run --rm `
            -v "${uploadVolume}:/app/uploads:ro" `
            alpine:3.20 `
            sh -c "find /app/uploads -type f | wc -l"

        $finishedAt = (Get-Date).ToUniversalTime()
        Write-Host "RESTauración aislada EXITOSA" -ForegroundColor Green
        Write-Host "Versión de Alembic verificable en restauración: $($dumpInfo.Trim())"
        Write-Host "Duración total: $([math]::Round(($finishedAt - $startedAt).TotalSeconds, 3)) segundos"
        return
    } finally {
        & docker rm -f $containerName 2>$null | Out-Null
        & docker volume rm $volumeName 2>$null | Out-Null
        & docker volume rm $uploadVolume 2>$null | Out-Null
    }
}

if (-not (Test-Path $EnvFile)) {
    throw "Falta $EnvFile. No se aplicará la restauración."
}
$composeArgs = @("compose", "--env-file", $EnvFile, "-f", $ComposeFile)
$apiContainer = (& docker @composeArgs ps -q api).Trim()
$dbContainer = (& docker @composeArgs ps -q db).Trim()
if (-not $apiContainer -or -not $dbContainer) {
    throw "El staging debe estar iniciado para aplicar una restauración."
}

Write-Warning "Esta operación reemplazará la base y las fotos actuales del staging local."
& docker @composeArgs stop api web kiosk
if ($LASTEXITCODE -ne 0) { throw "No se pudieron detener los servicios del staging." }

try {
    & docker cp $dumpPath "${dbContainer}:/tmp/gym-staging-restore.dump"
    if ($LASTEXITCODE -ne 0) { throw "No se pudo copiar el respaldo de PostgreSQL." }

    & docker exec $dbContainer psql `
        --username=gym_staging `
        --dbname=postgres `
        --command="DROP DATABASE IF EXISTS gym_staging WITH (FORCE)"
    if ($LASTEXITCODE -ne 0) { throw "No se pudo retirar la base actual del staging." }
    & docker exec $dbContainer createdb `
        --username=gym_staging `
        gym_staging
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la base de staging para restaurar." }
    & docker exec $dbContainer pg_restore `
        --verbose `
        --no-owner `
        --no-privileges `
        --dbname=gym_staging `
        --username=gym_staging `
        /tmp/gym-staging-restore.dump
    if ($LASTEXITCODE -ne 0) { throw "No se pudo restaurar PostgreSQL en staging." }
    & docker exec $dbContainer rm -f /tmp/gym-staging-restore.dump

    $archiveDir = Split-Path -Parent $uploadsPath
    & docker run --rm `
        --volumes-from $apiContainer `
        -v "${archiveDir}:/backup:ro" `
        alpine:3.20 `
        sh -c "rm -rf /app/uploads/* /app/uploads/.[!.]* /app/uploads/..?* 2>/dev/null || true; mkdir -p /app/uploads; tar -xzf /backup/uploads.tar.gz -C /app/uploads"
    if ($LASTEXITCODE -ne 0) { throw "No se pudo restaurar las fotos en staging." }
} finally {
    & docker @composeArgs up -d api web kiosk
}

Write-Host "RESTauración aplicada al staging local." -ForegroundColor Green
