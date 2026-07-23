import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import delete

from yolo_factory.api.app import create_app
from yolo_factory.config.models import TaskConfig
from yolo_factory.datasets.release import release_dataset
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task


class NoopDvc:
    def add(self, path: Path) -> None:
        assert path.is_dir()


def _orphan_release(storage: Path) -> str:
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json=json.dumps(["red"])))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="annotation-lights-native-1", task_id="lights", provider_project="native", provider_version="1", zip_path="annotations.zip", sha256="a" * 64))
    extracted = storage / "extracted"
    image = extracted / "train" / "images" / "sample.jpg"
    label = extracted / "train" / "labels" / "sample.txt"
    image.parent.mkdir(parents=True)
    label.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), "red").save(image)
    label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    result = release_dataset(
        TaskConfig(task_id="lights", task_type="detect", classes=["red"], annotation_format="yolo-detect"),
        "annotation-lights-native-1", "1.0.0", storage, registry, NoopDvc(), display_name="Lights",
    )
    with session_scope(registry) as session:
        session.execute(delete(DatasetRelease).where(DatasetRelease.id == result.release_id))
    return result.release_path.relative_to(storage).as_posix()


def test_scans_and_registers_valid_orphan_release(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    release_path = _orphan_release(storage)

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        scan = client.get("/api/dataset-releases/reconciliation")
        registered = client.post("/api/dataset-releases/reconciliation/register", json={"release_path": release_path})
        refreshed = client.get("/api/dataset-releases/reconciliation")

    assert scan.status_code == 200
    assert scan.json()[0]["status"] == "orphan_directory"
    assert scan.json()[0]["allowed_actions"] == ["register"]
    assert registered.status_code == 201
    assert registered.json()["id"] == "dataset-lights-1.0.0"
    assert refreshed.json()[0]["status"] == "healthy"


def test_rejects_registration_outside_managed_release_root(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.post("/api/dataset-releases/reconciliation/register", json={"release_path": "../outside"})

    assert response.status_code == 422
    assert "outside" in response.json()["detail"]
