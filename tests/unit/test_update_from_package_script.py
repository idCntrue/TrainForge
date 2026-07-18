from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_package_updater_stages_deploy_and_preserves_runtime_assets() -> None:
    script = (ROOT / "docker" / "update-from-package.sh").read_text(encoding="utf-8")

    assert "tar -tzf" in script
    assert "Unsafe archive path" in script
    assert 'cp "$PROJECT_DIR/.env" "$STAGED_PROJECT/.env"' in script
    assert "COMPOSE_PROJECT_NAME=yolo_model_factory" in script
    assert '"$STAGED_PROJECT/docker/deploy.sh"' in script
    assert "docker compose" not in script
    assert script.index('"$STAGED_PROJECT/docker/deploy.sh"') < script.index('mv "$PROJECT_DIR" "$BACKUP_DIR"')
    assert 'mv "$STAGED_PROJECT" "$PROJECT_DIR"' in script

    forbidden = [
        'rm -rf "$DATA_DIR"',
        'rm -rf "$MODEL_DIR"',
        "rm -rf /data",
        "rm -rf /models",
        "cp factory.db",
        "mv factory.db",
    ]
    assert all(command not in script for command in forbidden)


def test_package_updater_defaults_to_canonical_cloud_directory() -> None:
    script = (ROOT / "docker" / "update-from-package.sh").read_text(encoding="utf-8")

    assert 'PROJECT_DIR=${2:-/opt/yolo_model_factory}' in script
    assert "Source backup retained" in script
