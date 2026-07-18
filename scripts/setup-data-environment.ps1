param(
    [string]$EnvironmentPath = "$env:USERPROFILE\.venvs\yolo-data-pipeline-py310"
)

$ErrorActionPreference = "Stop"
$Python = Join-Path $EnvironmentPath "Scripts\python.exe"
$Requirements = Join-Path (Split-Path -Parent $PSScriptRoot) "requirements\data.txt"

if (-not (Test-Path -LiteralPath $Python)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $EnvironmentPath) | Out-Null
    py -3.10 -m venv $EnvironmentPath
}

& $Python -m pip install --upgrade pip
& $Python -m pip install --requirement $Requirements
& $Python -c "import cv2, datumaro; print('data environment ready')"

