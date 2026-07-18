[CmdletBinding()]
param(
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$SourceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$SourceParent = Split-Path $SourceRoot -Parent
$ProjectName = Split-Path $SourceRoot -Leaf

if (-not $OutputPath) {
    $OutputPath = Join-Path $SourceParent "yolo-model-factory-deploy.tar.gz"
}
$OutputPath = [System.IO.Path]::GetFullPath($OutputPath)

$stagingRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("trainforge-package-" + [guid]::NewGuid().ToString("N"))
$stagedProject = Join-Path $stagingRoot $ProjectName
New-Item -ItemType Directory -Path $stagedProject | Out-Null

$excludedDirectories = @(
    (Join-Path $SourceRoot ".git"),
    (Join-Path $SourceRoot ".codex"),
    (Join-Path $SourceRoot ".superpowers"),
    (Join-Path $SourceRoot ".worktrees"),
    (Join-Path $SourceRoot "artifacts"),
    (Join-Path $SourceRoot "logs"),
    (Join-Path $SourceRoot "runs"),
    (Join-Path $SourceRoot "registry"),
    (Join-Path $SourceRoot "models"),
    (Join-Path $SourceRoot "data"),
    (Join-Path $SourceRoot ".pytest_cache"),
    (Join-Path $SourceRoot ".venv"),
    (Join-Path $SourceRoot "frontend/node_modules"),
    (Join-Path $SourceRoot "frontend/dist")
)

$excludedFiles = @(
    ".env",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.pt",
    "*.pth",
    "*.ckpt",
    "*.onnx",
    "*.engine",
    "*.safetensors",
    "*.log",
    "*.zip",
    "*.tar",
    "*.tar.gz",
    "*.tgz",
    "*.pyc"
)

$requiredEntries = @(
    "compose.yaml",
    ".env.docker.example",
    "docker/deploy.sh",
    "docker/update-from-package.sh",
    "src/yolo_factory/api/app.py",
    "src/yolo_factory/registry/database.py",
    "src/yolo_factory/models/repository.py",
    "frontend/package.json"
)

try {
    $copyArguments = @(
        $SourceRoot,
        $stagedProject,
        "/E",
        "/R:1",
        "/W:1",
        "/NFL",
        "/NDL",
        "/NJH",
        "/NJS",
        "/NP",
        "/XD"
    ) + $excludedDirectories + @("/XF") + $excludedFiles

    & robocopy @copyArguments | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed with exit code $LASTEXITCODE"
    }

    Get-ChildItem -Path $stagedProject -Recurse -Force -File -Filter ".env*" |
        Where-Object { $_.Name -ne ".env.docker.example" } |
        Remove-Item -Force

    foreach ($entry in $requiredEntries) {
        $candidate = Join-Path $stagedProject ($entry -replace "/", [System.IO.Path]::DirectorySeparatorChar)
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "Missing required archive entry: $entry"
        }
    }

    tar -czf $OutputPath -C $stagingRoot $ProjectName
    if ($LASTEXITCODE -ne 0) {
        throw "tar failed with exit code $LASTEXITCODE"
    }

    $archiveEntries = @(tar -tzf $OutputPath)
    $forbiddenPattern = '(^|/)(\.git|\.codex|\.superpowers|\.worktrees|node_modules|dist|artifacts|logs|runs)(/|$)|(^|/)\.env$|\.(db|sqlite|sqlite3|pt|pth|ckpt|onnx|engine|safetensors|log|zip|tar|tgz)$'
    foreach ($entry in $archiveEntries) {
        if ($entry -match $forbiddenPattern) {
            throw "Forbidden archive entry: $entry"
        }
    }

    foreach ($entry in $requiredEntries) {
        $archiveEntry = "$ProjectName/$entry"
        if ($archiveEntry -notin $archiveEntries) {
            throw "Missing required archive entry: $archiveEntry"
        }
    }

    $archive = Get-Item -LiteralPath $OutputPath
    $hash = Get-FileHash -LiteralPath $OutputPath -Algorithm SHA256
    Write-Output "Deployment package: $($archive.FullName)"
    Write-Output "Size: $($archive.Length) bytes"
    Write-Output "SHA256: $($hash.Hash)"
}
finally {
    $resolvedTemp = [System.IO.Path]::GetFullPath($stagingRoot)
    $tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    if ($resolvedTemp.StartsWith($tempRoot) -and (Split-Path $resolvedTemp -Leaf).StartsWith("trainforge-package-")) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
