from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.unit.datasets.test_release import RecordingDvc, _arrange
from yolo_factory.api.app import create_app
from yolo_factory.datasets.release import release_dataset
from yolo_factory.registry.database import session_scope
from yolo_factory.registry.models import DatasetRelease


class FailingDvc(RecordingDvc):
    def add(self, path: Path) -> None:
        super().add(path)
        raise RuntimeError("DVC unavailable")


def test_dataset_release_rejects_overlapping_heavy_operation(tmp_path: Path) -> None:
    app = create_app(storage_root=tmp_path / "storage", training_engine="simulation")
    with TestClient(app) as client:
        with app.state.heavy_operation_guard.acquire("training-start"):
            response = client.post("/api/dataset-releases", json={
                "task_id": "lights",
                "annotation_import_id": "annotation-lights-1",
                "display_name": "Lights",
                "version": "1.0.0",
            })

    assert response.status_code == 409
    assert "heavy operation already active: training-start" in response.json()["detail"]


def test_dvc_failure_preserves_release_and_can_resume(tmp_path: Path) -> None:
    task, registry, storage = _arrange(tmp_path)
    with pytest.raises(RuntimeError, match="DVC unavailable"):
        release_dataset(
            task,
            "annotation-lights-rf-1",
            "1.0.0",
            storage,
            registry,
            FailingDvc(),
            display_name="电梯灯数据集",
        )
    release_path = storage / "dataset-releases" / "lights" / "dataset-v1.0.0"
    assert release_path.exists()
    with session_scope(registry) as session:
        release = session.get(DatasetRelease, "dataset-lights-1.0.0")
        assert release.status == "dvc_failed"

    dvc = RecordingDvc()
    result = release_dataset(
        task,
        "annotation-lights-rf-1",
        "1.0.0",
        storage,
        registry,
        dvc,
        display_name="电梯灯数据集",
    )
    assert result.status == "published"
    assert dvc.paths == [release_path]
