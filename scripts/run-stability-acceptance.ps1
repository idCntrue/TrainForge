param(
    [ValidateSet("short", "soak")]
    [string]$Mode = "short",
    [string]$Root = "",
    [double]$Hours = 8,
    [double]$DurationSeconds = 0
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($Root)) {
    $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $Root = Join-Path $env:TEMP "trainforge-stability\$Timestamp"
}

if ($DurationSeconds -le 0) {
    if ($Mode -eq "soak") {
        if ($Hours -le 0) {
            throw "Hours must be positive for soak acceptance"
        }
        $DurationSeconds = $Hours * 60 * 60
    }
    else {
        $DurationSeconds = 60
    }
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
Push-Location $ProjectRoot
try {
    & python -m yolo_factory.operations.acceptance `
        --root $Root `
        --duration-seconds $DurationSeconds `
        --sample-interval-seconds 1
    $ExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}

if ($ExitCode -ne 0) {
    exit $ExitCode
}

Write-Host "Stability acceptance passed: $Root"
