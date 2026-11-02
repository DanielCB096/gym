[CmdletBinding()]
param(
    [switch]$WithMobile
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env.staging.local"
$ComposeFile = Join-Path $Root "compose.staging.local.yml"
$PrepareScript = Join-Path $PSScriptRoot "prepare-local-staging.ps1"

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker Desktop no está instalado o no está disponible en PATH."
}

$dockerOs = & docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $dockerOs.Trim() -ne "linux") {
    throw "Docker Desktop debe estar iniciado con contenedores Linux para usar el staging local."
}

$memory = Get-CimInstance Win32_OperatingSystem
$freeMemoryMb = [math]::Floor($memory.FreePhysicalMemory / 1024)
$requiredMemoryMb = if ($WithMobile) { 5120 } else { 4096 }
if ($freeMemoryMb -lt $requiredMemoryMb) {
    throw "Hay ${freeMemoryMb} MB de RAM libre; libera al menos $requiredMemoryMb MB antes de construir el staging para evitar agotar la memoria del equipo."
}

if (-not (Test-Path $EnvFile)) {
    & $PrepareScript
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$composeArgs = @(
    "compose",
    "--env-file", $EnvFile,
    "-f", $ComposeFile
)
if ($WithMobile) {
    $composeArgs += @("--profile", "member-app")
}
$configArgs = @($composeArgs + @("config", "--quiet"))
& docker @configArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$buildServices = @("api", "web")
if ($WithMobile) {
    $buildServices += "member-app"
}
foreach ($service in $buildServices) {
    $buildArgs = @($composeArgs + @("build", $service))
    & docker @buildArgs
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$upArgs = @($composeArgs + @("up", "--detach"))
& docker @upArgs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$statusArgs = @($composeArgs + @("ps", "--all"))

function Wait-HttpEndpoint([string]$Name, [string]$Url, [datetime]$Deadline) {
    Write-Host "Esperando $Name..."
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return
            }
        } catch {
            Start-Sleep -Seconds 5
        }
    } while ((Get-Date) -lt $Deadline)

    $containerStatus = & docker @statusArgs
    throw "El endpoint de $Name no respondió en el tiempo esperado: $Url`n$containerStatus"
}

$deadline = (Get-Date).AddMinutes(3)
Wait-HttpEndpoint "API" "http://localhost:8010/health" $deadline
Wait-HttpEndpoint "panel" "http://localhost:3001" $deadline
Wait-HttpEndpoint "kiosco" "http://localhost:8090" $deadline
Wait-HttpEndpoint "Mailpit" "http://localhost:8025" $deadline
if ($WithMobile) {
    Wait-HttpEndpoint "app del socio" "http://localhost:8081" $deadline
}

Write-Host ""
Write-Host "STAGING LOCAL LISTO" -ForegroundColor Green
Write-Host "Panel:       http://localhost:3001"
Write-Host "API:         http://localhost:8010/docs"
Write-Host "Kiosco:      http://localhost:8090"
Write-Host "Correo test: http://localhost:8025"
if ($WithMobile) {
    Write-Host "App socio:   http://localhost:8081"
}
Write-Host ""
Write-Host "Solo usa datos sintéticos. Los servicios escuchan en localhost; el equipo debe permanecer encendido durante las pruebas."
Write-Host "Para detener sin borrar la base: docker compose --env-file .env.staging.local -f compose.staging.local.yml down"
