# Levanta la demo comercial completa sobre una copia desechable de la base de
# vista previa. No toca backend/gym_preview.db ni los seeds existentes.
#
#   powershell -ExecutionPolicy Bypass -File demo\start-demo.ps1
#   powershell -ExecutionPolicy Bypass -File demo\start-demo.ps1 -Reset
#   powershell -ExecutionPolicy Bypass -File demo\start-demo.ps1 -SkipSeeds
#   powershell -ExecutionPolicy Bypass -File demo\start-demo.ps1 -WithMobile
#
# Para apagarla: demo\stop-demo.ps1

[CmdletBinding()]
param(
    [switch]$Reset,
    [switch]$SkipSeeds,
    [switch]$WithMobile,
    [switch]$NoBrowser,
    [int]$BackendPort = 8010,
    [int]$WebPort = 3001,
    [int]$MobilePort = 8081,
    [int]$KioskPort = 8090,
    [string]$DemoPassword = "DemoGimnasio2026!"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root "backend"
$Web = Join-Path $Root "web"
$Mobile = Join-Path $Root "mobile"
$Kiosk = Join-Path $Root "kiosk"
$Runtime = Join-Path $Backend ".demo_runtime"
$Secrets = Join-Path $Backend ".secrets"
$Logs = Join-Path $Runtime "logs"
$DemoDb = Join-Path $Runtime "gym_preview.db"
$SourceDb = Join-Path $Backend "gym_preview.db"
$Python = Join-Path $Backend ".venv\Scripts\python.exe"
$PidFile = Join-Path $Secrets "demo-pids.json"
$TokenFile = Join-Path $Secrets "demo-kiosk-token.txt"
$pidFileCreated = $false

$SeedOrder = @(
    "classes",
    "physio",
    "routines",
    "maintenance",
    "reports",
    "member_accounts",
    "returns",
    "billing",
    "ppd",
    "reconciliation"
)

$started = @()

function Write-Step($message) {
    Write-Host ""
    Write-Host "== $message" -ForegroundColor Cyan
}

function Assert-FreePort([int]$port, [string]$name) {
    $listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        throw "El puerto $port ($name) ya esta ocupado. Cierra ese proceso o cambia el puerto con -${name}Port."
    }
}

function Wait-Endpoint {
    param(
        [string]$Url,
        [int]$TimeoutSeconds = 120,
        [System.Diagnostics.Process]$Process
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($Process -and $Process.HasExited) { return $false }
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) { return $true }
        } catch {
            # El servidor aun no escucha; se reintenta.
        }
        Start-Sleep -Milliseconds 800
    }
    return $false
}

function Show-LogTail([string]$path, [int]$lines = 25) {
    if (Test-Path $path) {
        Write-Host "  --- $path ---" -ForegroundColor DarkGray
        Get-Content $path -Tail $lines | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    }
}

function Start-LoggedProcess {
    param(
        [string]$FilePath,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$StdOut,
        [string]$StdErr
    )
    return Start-Process -FilePath $FilePath -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory -PassThru -WindowStyle Hidden `
        -RedirectStandardOutput $StdOut -RedirectStandardError $StdErr
}

function Stop-ProcessTree([int]$rootProcessId) {
    $processes = Get-CimInstance Win32_Process
    $tree = New-Object System.Collections.Generic.List[int]
    $pending = New-Object System.Collections.Generic.Stack[int]
    $pending.Push($rootProcessId)

    while ($pending.Count -gt 0) {
        $processId = $pending.Pop()
        $tree.Add($processId)
        foreach ($child in $processes | Where-Object { $_.ParentProcessId -eq $processId }) {
            $pending.Push([int]$child.ProcessId)
        }
    }

    for ($index = $tree.Count - 1; $index -ge 0; $index--) {
        Stop-Process -Id $tree[$index] -Force -ErrorAction SilentlyContinue
    }
}

try {
    if (-not (Test-Path $Python)) {
        throw "No existe el venv del backend: $Python. Crea backend/.venv e instala backend/requirements.txt."
    }
    if (-not (Test-Path (Join-Path $Web "node_modules"))) {
        throw "Falta web/node_modules. Ejecuta npm install en web/."
    }
    if ($WithMobile -and -not (Test-Path (Join-Path $Mobile "node_modules"))) {
        throw "Falta mobile/node_modules. Ejecuta npm install en mobile/."
    }

    Assert-FreePort $BackendPort "Backend"
    Assert-FreePort $WebPort "Web"
    Assert-FreePort $KioskPort "Kiosk"
    if ($WithMobile) { Assert-FreePort $MobilePort "Mobile" }
    if (Test-Path $PidFile) {
        throw "Ya existe un registro de la demo ($PidFile). Deten esa instancia antes de iniciar otra para no compartir ni reemplazar su base."
    }

    New-Item -ItemType Directory -Force $Runtime | Out-Null
    New-Item -ItemType Directory -Force $Logs | Out-Null
    New-Item -ItemType Directory -Force $Secrets | Out-Null

    if ($Reset -or -not (Test-Path $DemoDb)) {
        if (-not (Test-Path $SourceDb)) {
            throw "No existe la base sembrada $SourceDb. Restaurala o genera una vista previa antes de la demo."
        }
        Copy-Item $SourceDb $DemoDb -Force
        Write-Host "Base de demo creada desde gym_preview.db: $DemoDb" -ForegroundColor Green
    } else {
        Write-Host "Reutilizando la base de demo: $DemoDb (usa -Reset para recrearla)."
    }

    $env:PREVIEW_MODE = "true"
    $env:DATABASE_URL = "sqlite:///$($DemoDb -replace '\\', '/')"
    $env:APP_TIMEZONE = "America/Mexico_City"
    $env:WEB_ORIGIN = "http://localhost:$WebPort"
    $env:GYM_API_URL = "http://127.0.0.1:$BackendPort"
    $env:PROGRESS_PHOTOS_DIR = (Join-Path $Backend "uploads\progress_photos")
    $env:CORS_ORIGINS = @(
        "http://localhost:$WebPort",
        "http://127.0.0.1:$WebPort",
        "http://localhost:$MobilePort",
        "http://127.0.0.1:$MobilePort",
        "http://localhost:$KioskPort",
        "http://127.0.0.1:$KioskPort"
    ) -join ","
    $env:PYTHONPATH = (Join-Path $Backend "src")
    $env:VAPID_PRIVATE_KEY = ""
    $env:VAPID_SUBJECT = "mailto:avisos@centro-fit.local"

    if (-not $SkipSeeds) {
        Write-Step "Sembrando datos de la demo (base aislada)"
        Push-Location $Runtime
        try {
            foreach ($seed in $SeedOrder) {
                $script = Join-Path $Backend "seed_$seed.py"
                if (-not (Test-Path $script)) {
                    throw "Falta el seed requerido: $script."
                }
                Write-Host "  seed_$seed.py" -ForegroundColor DarkGray
                & $Python $script
                if ($LASTEXITCODE -ne 0) {
                    throw "Fallo seed_$seed.py (codigo $LASTEXITCODE)."
                }
            }
        } finally {
            Pop-Location
        }
    } else {
        Write-Step "Sembrado omitido (-SkipSeeds)"
    }

    Write-Step "Credenciales, kiosco y fechas de la demo"
    $seedDemoArgs = @("--db", $DemoDb, "--password", $DemoPassword)
    $seedDemoArgs += @("--token-file", $TokenFile)
    if ($SkipSeeds) { $seedDemoArgs += "--keep-kiosk" }
    & $Python (Join-Path $Backend "seed_demo.py") @seedDemoArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Fallo seed_demo.py (codigo $LASTEXITCODE)."
    }

    Write-Step "Arrancando backend en http://127.0.0.1:$BackendPort"
    $backendOut = Join-Path $Logs "backend.log"
    $backendErr = Join-Path $Logs "backend.err.log"
    $backendProc = Start-LoggedProcess -FilePath $Python `
        -Arguments "-m uvicorn app.main:app --app-dir src --host 127.0.0.1 --port $BackendPort" `
        -WorkingDirectory $Backend -StdOut $backendOut -StdErr $backendErr
    $started += $backendProc
    if (-not (Wait-Endpoint -Url "http://127.0.0.1:$BackendPort/health" -TimeoutSeconds 90 -Process $backendProc)) {
        Show-LogTail $backendOut
        Show-LogTail $backendErr
        throw "El backend no respondio en 90 s."
    }
    Write-Host "  backend listo." -ForegroundColor Green

    Write-Step "Arrancando panel en http://localhost:$WebPort"
    $webOut = Join-Path $Logs "web.log"
    $webErr = Join-Path $Logs "web.err.log"
    $webProc = Start-LoggedProcess -FilePath "cmd.exe" `
        -Arguments "/c npm run dev -- -p $WebPort --hostname 127.0.0.1" `
        -WorkingDirectory $Web -StdOut $webOut -StdErr $webErr
    $started += $webProc
    if (-not (Wait-Endpoint -Url "http://localhost:$WebPort" -TimeoutSeconds 150 -Process $webProc)) {
        Show-LogTail $webOut
        Show-LogTail $webErr
        throw "El panel no respondio en 150 s."
    }
    Write-Host "  panel listo." -ForegroundColor Green

    Write-Step "Arrancando kiosco en http://localhost:$KioskPort"
    $kioskOut = Join-Path $Logs "kiosk.log"
    $kioskErr = Join-Path $Logs "kiosk.err.log"
    $kioskProc = Start-LoggedProcess -FilePath $Python `
        -Arguments "-m http.server $KioskPort --bind 127.0.0.1 --directory `"$Kiosk`"" `
        -WorkingDirectory $Root -StdOut $kioskOut -StdErr $kioskErr
    $started += $kioskProc
    if (-not (Wait-Endpoint -Url "http://localhost:$KioskPort" -TimeoutSeconds 30 -Process $kioskProc)) {
        Show-LogTail $kioskOut
        Show-LogTail $kioskErr
        throw "El kiosco no respondio en 30 s."
    }
    Write-Host "  kiosco listo." -ForegroundColor Green

    $mobileProc = $null
    if ($WithMobile) {
        Write-Step "Arrancando app del socio (Expo web) en http://localhost:$MobilePort"
        $env:EXPO_PUBLIC_API_URL = "http://127.0.0.1:$BackendPort"
        $env:EXPO_NO_TELEMETRY = "1"
        $env:BROWSER = "none"
        $mobileOut = Join-Path $Logs "mobile.log"
        $mobileErr = Join-Path $Logs "mobile.err.log"
        $mobileProc = Start-LoggedProcess -FilePath "cmd.exe" `
            -Arguments "/c npm run web -- --port $MobilePort --host localhost" `
            -WorkingDirectory $Mobile -StdOut $mobileOut -StdErr $mobileErr
        $started += $mobileProc
        if (-not (Wait-Endpoint -Url "http://localhost:$MobilePort" -TimeoutSeconds 180 -Process $mobileProc)) {
            Show-LogTail $mobileOut
            Show-LogTail $mobileErr
            throw "La app del socio no respondio en 180 s."
        }
        Write-Host "  app del socio lista." -ForegroundColor Green
    }

    $pidPayload = @{
        backend = $backendProc.Id
        web = $webProc.Id
        kiosk = $kioskProc.Id
        mobile = $(if ($mobileProc) { $mobileProc.Id } else { $null })
        started_at = (Get-Date).ToString("o")
        process_started_at = @{
            backend = $backendProc.StartTime.ToString("o")
            web = $webProc.StartTime.ToString("o")
            kiosk = $kioskProc.StartTime.ToString("o")
            mobile = $(if ($mobileProc) { $mobileProc.StartTime.ToString("o") } else { $null })
        }
        backend_port = $BackendPort
        web_port = $WebPort
        kiosk_port = $KioskPort
        mobile_port = $MobilePort
    }
    $pidPayload | ConvertTo-Json | Set-Content -Encoding UTF8 $PidFile
    $pidFileCreated = $true

    $kioskToken = ""
    if (Test-Path $TokenFile) { $kioskToken = (Get-Content $TokenFile -Raw).Trim() }

    Write-Host ""
    Write-Host "DEMO LISTA" -ForegroundColor Green
    Write-Host "  Panel:   http://localhost:$WebPort" -ForegroundColor White
    Write-Host "  API:     http://127.0.0.1:$BackendPort/docs" -ForegroundColor White
    Write-Host "  Kiosco:  http://localhost:$KioskPort" -ForegroundColor White
    if ($WithMobile) {
        Write-Host "  App:     http://localhost:$MobilePort" -ForegroundColor White
    }
    Write-Host ""
    Write-Host "  Cuentas (contrasena: $DemoPassword)" -ForegroundColor White
    Write-Host "    dueno          owner@centrofit.mx"
    Write-Host "    gerente        gerente@centrofit.mx"
    Write-Host "    recepcion      recepcion@centrofit.mx"
    Write-Host "    entrenador     carlos.ortiz@centrofit.mx"
    Write-Host "    mantenimiento  mantenimiento.preview@centrofit.mx"
    Write-Host ""
    Write-Host "  Socio para la app: ana.lopez@example.com (el codigo OTP se muestra en pantalla)."
    if ($kioskToken) {
        Write-Host "  Token del kiosco: $kioskToken" -ForegroundColor Yellow
        Write-Host "  (tambien en $TokenFile)"
    }
    Write-Host ""
    Write-Host "  Guion de la demo: demo/GUION-DEMO.md"
    Write-Host "  Logs: $Logs"
    Write-Host "  Para apagar: powershell -ExecutionPolicy Bypass -File demo/stop-demo.ps1"
    Write-Host ""

    if (-not $NoBrowser) {
        Start-Process "http://localhost:$WebPort"
    }
} catch {
    Write-Host ""
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    foreach ($process in $started) {
        if ($process -and -not $process.HasExited) {
            Stop-ProcessTree -rootProcessId $process.Id
        }
    }
    if ($pidFileCreated -and (Test-Path $PidFile)) {
        Remove-Item -LiteralPath $PidFile -Force
    }
    throw
}
