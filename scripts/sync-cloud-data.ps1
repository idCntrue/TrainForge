[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RemoteHost,
    [string]$RemoteProject = "/opt/yolo_model_factory",
    [string]$RemoteDataRoot = "/srv/yolo-factory/data",
    [string]$RemoteModelRoot = "/srv/yolo-factory/models",
    [string]$LocalDataRoot = "D:\YOLO_DATA",
    [int]$ApiPort = 8000,
    [int]$WebPort = 53257,
    [switch]$IncludeModels,
    [switch]$IncludeRawVideos,
    [switch]$IncludeTrainingRuns,
    [switch]$Full,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LocalDataRoot = [System.IO.Path]::GetFullPath($LocalDataRoot)
$registryDirectory = Join-Path $LocalDataRoot "registry"
$localDatabase = Join-Path $registryDirectory "factory.db"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stagingRoot = Join-Path $LocalDataRoot ".cloud-sync-$stamp"
$stagedDatabase = Join-Path $stagingRoot "factory.cloud-copy.db"
$candidateDatabase = Join-Path $stagingRoot "factory.migrating.db"
$localBackup = Join-Path $registryDirectory "factory.before-cloud-sync-$stamp.db"
$requiredDirectories = @("frame-batches", "dataset-releases", "task-configs")
$optionalDataDirectories = @()
$localApiWasRunning = $false
$databaseReplaced = $false
$syncSucceeded = $false

if ($Full) {
    $IncludeModels = $true
    $IncludeRawVideos = $true
    $IncludeTrainingRuns = $true
}
if ($IncludeRawVideos) { $optionalDataDirectories += "raw-videos" }
if ($IncludeTrainingRuns) { $optionalDataDirectories += "training-runs" }
$dataDirectories = @($requiredDirectories + $optionalDataDirectories)

function Require-Command([string]$Name) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) { throw "Required command not found: $Name" }
    return $command
}

function Invoke-Native([string]$Executable, [string[]]$Arguments) {
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed with exit code $LASTEXITCODE"
    }
}

function Test-SqliteDatabase([string]$Path, $Python) {
    $code = "import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); result=db.execute('PRAGMA integrity_check').fetchone()[0]; db.close(); print(result); raise SystemExit(0 if result == 'ok' else 2)"
    $result = & $Python.Source -c $code $Path
    if ($LASTEXITCODE -ne 0 -or ($result | Select-Object -Last 1) -ne "ok") {
        throw "SQLite integrity check failed: $Path"
    }
}

function Stop-LocalApi {
    $listeners = @(Get-NetTCPConnection -LocalPort $ApiPort -State Listen -ErrorAction SilentlyContinue)
    if (-not $listeners) { return $false }
    foreach ($listener in $listeners) {
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction Stop
    }
    Start-Sleep -Milliseconds 500
    return $true
}

function Start-LocalApplication {
    $startScript = Join-Path $ProjectRoot "scripts/start-ui.ps1"
    & $startScript -ApiPort $ApiPort -WebPort $WebPort
    $health = Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 5
    if ($health.status -ne "ok") { throw "Local API health check failed" }
}

function Merge-StagedDirectory([string]$Name) {
    $source = Join-Path $stagingRoot $Name
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Required staged directory is missing: $Name"
    }
    $target = Join-Path $LocalDataRoot $Name
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    & robocopy $source $target /E /R:2 /W:2 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed for $Name with exit code $LASTEXITCODE" }
}

$ssh = Require-Command "ssh.exe"
$scp = Require-Command "scp.exe"
$python = Require-Command "python.exe"
$factory = Require-Command "yolo-factory.exe"
Require-Command "robocopy.exe" | Out-Null

Write-Host "Cloud source: $RemoteHost"
Write-Host "Local storage: $LocalDataRoot"
Write-Host "Required data: $($dataDirectories -join ', ')"
Write-Host "Models: $([bool]$IncludeModels)"

if ($DryRun) {
    Write-Host "Dry run complete. No remote or local data was changed."
    return
}

$drive = [System.IO.DriveInfo]::new([System.IO.Path]::GetPathRoot($LocalDataRoot))
Write-Host ("Local free space: {0:N1} GiB" -f ($drive.AvailableFreeSpace / 1GB))
New-Item -ItemType Directory -Force -Path $registryDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null

try {
    $sizePaths = @($dataDirectories | ForEach-Object { "$RemoteDataRoot/$_" })
    if ($IncludeModels) { $sizePaths += $RemoteModelRoot }
    Invoke-Native $ssh.Source @($RemoteHost, "du -sh $($sizePaths -join ' ') 2>/dev/null || true")

    $remotePython = @"
import hashlib
import sqlite3
from pathlib import Path
source_path = Path('/data/registry/factory.db')
copy_path = Path('/data/registry/factory.local-copy.db')
copy_path.unlink(missing_ok=True)
src = sqlite3.connect(source_path)
dst = sqlite3.connect(copy_path)
src.backup(dst)
dst.close()
src.close()
check = sqlite3.connect(copy_path)
result = check.execute('PRAGMA integrity_check').fetchone()[0]
check.close()
digest = hashlib.sha256(copy_path.read_bytes()).hexdigest()
print(f'{result}|{copy_path.stat().st_size}|{digest}')
raise SystemExit(0 if result == 'ok' else 2)
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($remotePython))
    $remoteBackupCommand = "cd $RemoteProject && echo $encoded | base64 -d | sudo docker compose exec -T api python3.10 -"
    Invoke-Native $ssh.Source @("-t", $RemoteHost, $remoteBackupCommand)

    Invoke-Native $scp.Source @("${RemoteHost}:$RemoteDataRoot/registry/factory.local-copy.db", $stagedDatabase)
    Test-SqliteDatabase $stagedDatabase $python

    if ($localDatabase -and (Test-Path -LiteralPath $localDatabase -PathType Leaf)) {
        Test-SqliteDatabase $localDatabase $python
    }

    $localApiWasRunning = Stop-LocalApi

    if (Test-Path -LiteralPath $localDatabase -PathType Leaf) {
        $backupCode = "import sqlite3,sys; src=sqlite3.connect(sys.argv[1]); dst=sqlite3.connect(sys.argv[2]); src.backup(dst); dst.close(); src.close()"
        & $python.Source -c $backupCode $localDatabase $localBackup
        if ($LASTEXITCODE -ne 0) { throw "Failed to back up local database" }
        Test-SqliteDatabase $localBackup $python
    }

    foreach ($directory in $dataDirectories) {
        Invoke-Native $scp.Source @("-r", "${RemoteHost}:$RemoteDataRoot/$directory", $stagingRoot)
        Merge-StagedDirectory $directory
    }
    if ($IncludeModels) {
        Invoke-Native $scp.Source @("-r", "${RemoteHost}:$RemoteModelRoot", $stagingRoot)
        Merge-StagedDirectory "models"
    }

    Copy-Item -LiteralPath $stagedDatabase -Destination $candidateDatabase -Force
    $previewOutput = & $factory.Source migrate-storage-paths --database $candidateDatabase --old-root "/data" --new-root $LocalDataRoot
    if ($LASTEXITCODE -ne 0) { throw "Storage-path migration preview failed" }
    $preview = ($previewOutput -join [Environment]::NewLine) | ConvertFrom-Json
    $selectedRoots = @($dataDirectories | ForEach-Object { [System.IO.Path]::GetFullPath((Join-Path $LocalDataRoot $_)) })
    $blockingMissingPaths = @($preview.missing_paths | Where-Object {
        $missingPath = [System.IO.Path]::GetFullPath([string]$_)
        @($selectedRoots | Where-Object { $missingPath.StartsWith($_, [System.StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
    })
    if ($blockingMissingPaths.Count -gt 0) {
        throw "Required synchronized paths are missing; staging retained for review: $($blockingMissingPaths.Count)"
    }
    $optionalMissingPaths = @($preview.missing_paths | Where-Object { $_ -notin $blockingMissingPaths })
    if ($optionalMissingPaths.Count -gt 0) {
        Write-Warning "Optional historical paths were not synchronized: $($optionalMissingPaths.Count)"
    }

    $applyOutput = & $factory.Source migrate-storage-paths --database $candidateDatabase --old-root "/data" --new-root $LocalDataRoot --apply
    if ($LASTEXITCODE -ne 0) { throw "Storage-path migration apply failed" }
    $applied = ($applyOutput -join [Environment]::NewLine) | ConvertFrom-Json
    Test-SqliteDatabase $candidateDatabase $python

    Move-Item -LiteralPath $candidateDatabase -Destination $localDatabase -Force
    $databaseReplaced = $true
    Test-SqliteDatabase $localDatabase $python
    Start-LocalApplication
    $syncSucceeded = $true

    Write-Host "Cloud-to-local sync completed."
    Write-Host "Updated database values: $($applied.updated_values)"
    if (Test-Path -LiteralPath $localBackup) { Write-Host "Local database backup: $localBackup" }
}
catch {
    Write-Error $_
    if ($databaseReplaced -and (Test-Path -LiteralPath $localBackup -PathType Leaf)) {
        Copy-Item -LiteralPath $localBackup -Destination $localDatabase -Force
        $databaseReplaced = $false
        Write-Warning "The original local database was restored."
    }
    throw
}
finally {
    if (-not $syncSucceeded) {
        Write-Warning "Retaining staging directory for diagnosis: $stagingRoot"
    }
    if (($localApiWasRunning -or $databaseReplaced) -and -not $syncSucceeded) {
        try { Start-LocalApplication } catch { Write-Warning "Local application restart failed: $($_.Exception.Message)" }
    }
    if ($syncSucceeded -and (Test-Path -LiteralPath $stagingRoot)) {
        Remove-Item -LiteralPath $stagingRoot -Recurse -Force
    }
}
