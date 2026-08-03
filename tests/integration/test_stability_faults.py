import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yolo_factory.api.app import create_app
from yolo_factory.api.jobs import JobTracker
from yolo_factory.common.operation_guard import HeavyOperationGuard
from yolo_factory.operations.database_backup import DatabaseBackupService
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import BackgroundJobRecord, Task


def test_api_restart_recovers_jobs_only_once(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    tracker = JobTracker(registry)
    job_id = tracker.create_job("abandoned")
    tracker.update_job(job_id, status="running")

    with TestClient(create_app(storage_root=storage, training_engine="simulation")):
        with session_scope(registry) as session:
            first_finished_at = session.get(BackgroundJobRecord, job_id).finished_at

    with TestClient(create_app(storage_root=storage, training_engine="simulation")):
        with session_scope(registry) as session:
            recovered = session.get(BackgroundJobRecord, job_id)
            assert recovered.status == "interrupted"
            assert recovered.finished_at == first_finished_at


def test_expired_lease_is_reclaimed_after_previous_owner_disappears(tmp_path: Path) -> None:
    registry = create_registry(tmp_path / "factory.db")
    first = HeavyOperationGuard(registry, lease_seconds=0.05)
    first._acquire_lease("abandoned")
    time.sleep(0.06)

    replacement = HeavyOperationGuard(registry, lease_seconds=1)
    with replacement.acquire("replacement"):
        assert replacement.active_operation == "replacement"


def test_backup_replace_failure_leaves_live_registry_queryable(tmp_path: Path) -> None:
    database = tmp_path / "registry" / "factory.db"
    registry = create_registry(database)
    with session_scope(registry) as session:
        session.add(Task(
            id="lights",
            task_type="detect",
            annotation_format="yolo-detect",
            classes_json='["light"]',
        ))
    backup_root = database.parent / "backups"
    service = DatabaseBackupService(
        registry,
        database,
        backup_root,
        retention=2,
        replace_file=lambda source, destination: (_ for _ in ()).throw(OSError("disk write failed")),
    )

    with pytest.raises(OSError, match="disk write failed"):
        service.create()

    with session_scope(registry) as session:
        assert session.get(Task, "lights") is not None
    assert list(backup_root.glob("*.tmp")) == []
    assert list(backup_root.glob("*.db")) == []
