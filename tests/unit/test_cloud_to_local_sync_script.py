from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "sync-cloud-data.ps1"


def _script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_sync_script_defaults_to_training_ready_data_without_server_identity() -> None:
    script = _script()

    assert "[Parameter(Mandatory = $true)]" in script
    assert "[string]$RemoteHost" in script
    assert '[string]$LocalDataRoot = "D:\\YOLO_DATA"' in script
    assert '"frame-batches"' in script
    assert '"dataset-releases"' in script
    assert '"task-configs"' in script
    assert "[switch]$IncludeModels" in script
    assert "[switch]$IncludeRawVideos" in script
    assert "[switch]$IncludeTrainingRuns" in script
    assert "[switch]$Full" in script
    assert "121.40.214.229" not in script


def test_sync_script_treats_cloud_database_as_read_only_source() -> None:
    script = _script()

    assert "/data/registry/factory.db" in script
    assert "/data/registry/factory.local-copy.db" in script
    assert "src.backup(dst)" in script
    assert "PRAGMA integrity_check" in script
    assert "rm -rf /data" not in script
    assert "rm /data/registry/factory.db" not in script
    assert "unlink('/data/registry/factory.db')" not in script


def test_sync_script_backs_up_and_verifies_local_candidate_before_replacement() -> None:
    script = _script()

    backup = script.index("factory.before-cloud-sync-")
    migrate = script.index("migrate-storage-paths")
    replace = script.index("Move-Item -LiteralPath $candidateDatabase")
    restart = script.rindex("Start-LocalApplication")

    assert backup < migrate < replace < restart
    assert script.count("PRAGMA integrity_check") >= 2
    assert '"/data"' in script
    assert "$LocalDataRoot" in script
    assert "missing_paths" in script


def test_sync_script_has_failure_recovery_and_dry_run() -> None:
    script = _script()

    assert "[switch]$DryRun" in script
    assert "finally" in script
    assert "$localApiWasRunning" in script
    assert "$databaseReplaced" in script
    assert "Retaining staging directory" in script


def test_sync_script_reports_errors_without_skipping_database_rollback() -> None:
    script = _script()

    report = script.index('Write-Error $_ -ErrorAction Continue')
    restore = script.index('Copy-Item -LiteralPath $localBackup -Destination $localDatabase -Force')

    assert report < restore


def test_sync_script_only_blocks_missing_training_ready_paths() -> None:
    script = _script()

    assert "$blockingMissingPaths" in script
    assert '"frame-batches"' in script
    assert '"dataset-releases"' in script
    assert "Optional historical paths were not synchronized" in script
