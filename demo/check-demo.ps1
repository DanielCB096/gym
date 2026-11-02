# Comprueba que la demo esta arriba antes de que entre el cliente.
#
#   powershell -ExecutionPolicy Bypass -File demo\check-demo.ps1

[CmdletBinding()]
param(
    [int]$BackendPort = 8010,
    [int]$WebPort = 3001,
    [int]$KioskPort = 8090,
    [int]$MobilePort = 8081,
    [string]$DemoPassword = "DemoGimnasio2026!"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$TokenFile = Join-Path $Root "backend\.secrets\demo-kiosk-token.txt"
$failures = 0

function Pass([string]$message) {
    Write-Host "  OK   $message" -ForegroundColor Green
}

function Fail([string]$message) {
    Write-Host "  FALLA $message" -ForegroundColor Red
    $script:failures++
}

function Try-Check([string]$name, [scriptblock]$check) {
    try {
        & $check
        Pass $name
    } catch {
        Fail "$name -> $($_.Exception.Message)"
    }
}

Write-Host ""
Write-Host "Chequeo de la demo" -ForegroundColor Cyan

Try-Check "Backend /health" {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/health" -TimeoutSec 5
    if (-not $health.preview_mode) { throw "el backend no esta en modo vista previa" }
}

Try-Check "Panel administrativo" {
    $response = Invoke-WebRequest -Uri "http://localhost:$WebPort" -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -ne 200) { throw "HTTP $($response.StatusCode)" }
}

Try-Check "Kiosco estatico" {
    $response = Invoke-WebRequest -Uri "http://localhost:$KioskPort" -UseBasicParsing -TimeoutSec 10
    if ($response.StatusCode -ne 200) { throw "HTTP $($response.StatusCode)" }
}

Try-Check "Base de demo y token del kiosco" {
    $db = Join-Path $Root "backend\.demo_runtime\gym_preview.db"
    if (-not (Test-Path $db)) { throw "falta $db" }
    if (-not (Test-Path $TokenFile)) { throw "falta $TokenFile" }
    $token = (Get-Content $TokenFile -Raw).Trim()
    if (-not $token) { throw "el token esta vacio" }
    $equipment = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/kiosk/equipment" -Headers @{ "X-Kiosk-Token" = $token } -TimeoutSec 10
    if ($null -eq $equipment.items) { throw "respuesta inesperada del kiosco" }
}

Try-Check "Login del panel y dashboard" {
    $body = @{ email = "owner@centrofit.mx"; password = $DemoPassword } | ConvertTo-Json
    $login = Invoke-WebRequest -Method Post -Uri "http://localhost:$WebPort/api/auth/login" `
        -ContentType "application/json" -Body $body -Headers @{ Origin = "http://localhost:$WebPort" } `
        -SessionVariable session -UseBasicParsing -TimeoutSec 15
    if ($login.StatusCode -ne 200) { throw "login HTTP $($login.StatusCode)" }
    $dashboard = Invoke-WebRequest -Uri "http://localhost:$WebPort/api/admin/dashboard" `
        -WebSession $session -UseBasicParsing -TimeoutSec 15
    if ($dashboard.StatusCode -ne 200) { throw "dashboard HTTP $($dashboard.StatusCode)" }
}

Try-Check "OTP de la app del socio" {
    $body = @{ email = "ana.lopez@example.com" } | ConvertTo-Json
    $response = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$BackendPort/member/auth/request-code" `
        -ContentType "application/json" -Body $body -TimeoutSec 10
    if (-not $response.preview_code) { throw "la vista previa no devolvio preview_code" }
}

$mobileUp = $false
try {
    $response = Invoke-WebRequest -Uri "http://localhost:$MobilePort" -UseBasicParsing -TimeoutSec 5
    $mobileUp = $response.StatusCode -eq 200
} catch {
    $mobileUp = $false
}
if ($mobileUp) {
    Pass "App del socio (Expo web)"
} else {
    Write-Host "  AVISO La app del socio no esta arriba (arranca con -WithMobile)." -ForegroundColor Yellow
}

Write-Host ""
if ($failures -eq 0) {
    Write-Host "Todo listo para la demo." -ForegroundColor Green
    exit 0
}

Write-Host "$failures comprobacion(es) fallaron. Revisa los logs en backend\.demo_runtime\logs\." -ForegroundColor Red
exit 1
