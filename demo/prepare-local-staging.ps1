[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$EnvFile = Join-Path $Root ".env.staging.local"

if (Test-Path $EnvFile) {
    throw "Ya existe $EnvFile. No se sobrescribió; conserva los secretos y vuelve a usarlo."
}

function New-RandomHex([int]$byteCount) {
    $bytes = New-Object byte[] $byteCount
    $random = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($bytes)
    } finally {
        $random.Dispose()
    }
    return (($bytes | ForEach-Object { $_.ToString("x2") }) -join "")
}

$lines = @(
    "STAGING_DB_PASSWORD=$(New-RandomHex 32)"
    "STAGING_SECRET_KEY=$(New-RandomHex 64)"
    "SMTP_HOST=mailpit"
    "SMTP_PORT=1025"
    "SMTP_USER="
    "SMTP_PASSWORD="
    "SMTP_FROM=staging@centrofit.local"
    "SMTP_USE_TLS=false"
    "SMTP_USE_SSL=false"
)
[System.IO.File]::WriteAllLines($EnvFile, $lines, [System.Text.Encoding]::ASCII)
Write-Host "Secretos locales de staging generados en $EnvFile (archivo ignorado por Git)." -ForegroundColor Green
