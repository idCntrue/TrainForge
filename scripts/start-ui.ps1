param(
    [int]$ApiPort = 8000,
    [int]$WebPort = 53257
)

$ErrorActionPreference = "Stop"
$Repository = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $env:USERPROFILE "AppData\Local\Programs\Python\Python310\python.exe"
$env:PYTHONPATH = "src"

function Test-HttpEndpoint([string]$Url) {
    try {
        $response = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Test-Port([int]$Port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python 3.10 not found: $Python"
}

$ApiArguments = @(
    "-m", "uvicorn",
    "yolo_factory.api.app:create_app",
    "--factory",
    "--host", "127.0.0.1",
    "--port", $ApiPort
)
$WebArguments = @(
    "run", "dev", "--",
    "--host", "127.0.0.1",
    "--port", $WebPort,
    "--strictPort"
)

$LogRoot = Join-Path $Repository "logs\ui"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

if (-not (Test-HttpEndpoint "http://127.0.0.1:$ApiPort/api/health")) {
    if (Test-Port $ApiPort) {
        throw "Port $ApiPort is occupied by another service. Stop it or choose another ApiPort."
    }
    $apiOut = Join-Path $LogRoot "api.out.log"
    $apiErr = Join-Path $LogRoot "api.err.log"
    $apiStart = @{ FilePath = $Python; ArgumentList = $ApiArguments; WorkingDirectory = $Repository; WindowStyle = "Hidden"; RedirectStandardOutput = $apiOut; RedirectStandardError = $apiErr }
    Start-Process @apiStart
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-HttpEndpoint "http://127.0.0.1:$ApiPort/api/health") { $ready = $true; break }
    }
    if (-not $ready) {
        $errorLog = Get-Content (Join-Path $LogRoot "api.err.log") -Raw -ErrorAction SilentlyContinue
        throw "API startup failed. Log: $errorLog"
    }
}

if (-not (Test-HttpEndpoint "http://127.0.0.1:$WebPort")) {
    if (Test-Port $WebPort) {
        throw "Port $WebPort is occupied by another service. Stop it or choose another WebPort."
    }
    $webOut = Join-Path $LogRoot "web.out.log"
    $webErr = Join-Path $LogRoot "web.err.log"
    $webStart = @{ FilePath = "npm.cmd"; ArgumentList = $WebArguments; WorkingDirectory = (Join-Path $Repository "frontend"); WindowStyle = "Hidden"; RedirectStandardOutput = $webOut; RedirectStandardError = $webErr }
    Start-Process @webStart
    $ready = $false
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-HttpEndpoint "http://127.0.0.1:$WebPort") { $ready = $true; break }
    }
    if (-not $ready) {
        $errorLog = Get-Content (Join-Path $LogRoot "web.err.log") -Raw -ErrorAction SilentlyContinue
        throw "Web startup failed. Log: $errorLog"
    }
}

Write-Host "API: http://127.0.0.1:$ApiPort/api/health"
Write-Host "Web: http://127.0.0.1:$WebPort"
