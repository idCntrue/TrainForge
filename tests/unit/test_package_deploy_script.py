from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_deploy_packager_uses_root_scoped_exclusions_and_checks_python_packages() -> None:
    script = (ROOT / "scripts" / "package-deploy.ps1").read_text(encoding="utf-8")

    assert 'Join-Path $SourceRoot "registry"' in script
    assert 'Join-Path $SourceRoot "models"' in script
    assert '"src/yolo_factory/registry/database.py"' in script
    assert '"src/yolo_factory/models/repository.py"' in script
    assert '"scripts/sync-cloud-data.ps1"' in script
    assert "Forbidden archive entry" in script
    assert "Missing required archive entry" in script


def test_deploy_packager_never_includes_runtime_or_sensitive_file_types() -> None:
    script = (ROOT / "scripts" / "package-deploy.ps1").read_text(encoding="utf-8")

    for pattern in ("*.db", "*.sqlite", "*.pt", "*.onnx", ".env", "*.log"):
        assert f'"{pattern}"' in script


def test_deploy_packager_removes_ignored_local_system_config() -> None:
    script = (ROOT / "scripts" / "package-deploy.ps1").read_text(encoding="utf-8")

    assert 'Join-Path $stagedProject "configs/system.yaml"' in script
    assert '"signal-light-detect.yaml"' in script
    assert '"signal-light-segment.yaml"' in script
    assert "Unexpected task config in archive" in script
