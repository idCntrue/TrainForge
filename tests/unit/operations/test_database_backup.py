from pathlib import Path

import pytest

from yolo_factory.common.hashing import sha256_file
from yolo_factory.operations.database_backup import DatabaseBackupError, DatabaseBackupService
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import Task


def _database(tmp_path: Path):
    database = tmp_path / "registry" / "factory.db"
    registry = create_registry(database)
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json='["light"]'))
    return database, registry


def test_backup_verifies_copy_without_replacing_live_business_data(tmp_path: Path) -> None:
    database, registry = _database(tmp_path)

    result = DatabaseBackupService(registry, database, database.parent / "backups", retention=2).create()

    with session_scope(registry) as session:
        assert session.get(Task, "lights") is not None
    assert result.integrity_check == "ok"
    assert result.path.is_file()
    assert result.sha256 == sha256_file(result.path)


def test_failed_integrity_removes_only_staging_backup(tmp_path: Path) -> None:
    database, registry = _database(tmp_path)
    backup_root = database.parent / "backups"
    service = DatabaseBackupService(
        registry, database, backup_root, retention=2, integrity_check=lambda _: "malformed",
    )

    with pytest.raises(DatabaseBackupError, match="integrity check failed"):
        service.create()

    assert database.is_file()
    assert list(backup_root.glob("*.tmp")) == []


def test_retention_deletes_only_oldest_managed_backups(tmp_path: Path) -> None:
    database, registry = _database(tmp_path)
    backup_root = database.parent / "backups"
    backup_root.mkdir(parents=True)
    operator_file = backup_root / "keep.txt"
    operator_file.write_text("operator file", encoding="utf-8")
    service = DatabaseBackupService(registry, database, backup_root, retention=2)

    service.create()
    service.create()
    service.create()

    assert len(service.list()) == 2
    assert operator_file.exists()


def test_backup_root_must_stay_below_registry_directory(tmp_path: Path) -> None:
    database, registry = _database(tmp_path)

    with pytest.raises(ValueError, match="backup directory"):
        DatabaseBackupService(registry, database, tmp_path / "outside", retention=2)
