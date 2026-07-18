from pathlib import Path

from fastapi.testclient import TestClient

from tests.integration.test_native_annotation_api import _storage
from yolo_factory.api.app import create_app


class PassingSam:
    def run(self, frame_id: str, payload: dict):
        assert payload["model"] in {"sam2_t.pt", "sam2_s.pt"}
        assert payload["point"] == [0.5, 0.5]
        return {"polygon": [0.1, 0.1, 0.9, 0.1, 0.5, 0.9], "model": payload["model"]}, Path(payload["image_path"]).parent


def test_sam_suggestion_creates_persisted_polygon(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    # The shared fixture is detect; switch task contract to segment for SAM.
    from yolo_factory.registry.database import create_registry, session_scope
    from yolo_factory.registry.models import Task
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        task = session.get(Task, "inspection")
        task.task_type = "segment"
        task.annotation_format = "yolo-seg"
    with TestClient(create_app(storage_root=storage, training_engine="simulation", sam_executor=PassingSam())) as client:
        client.post("/api/annotation-images/sync", json={"task_id": "inspection"})
        response = client.post("/api/annotation-images/frame/sam", json={"revision": 0, "class_id": 0, "class_name": "door", "model": "sam2_t.pt", "point": [0.5, 0.5]})
        assert response.status_code == 201
        assert response.json()["shapes"][0]["source"] == "sam2"
        assert response.json()["shapes"][0]["shape_type"] == "polygon"


class PreviewSam:
    def run(self, frame_id: str, payload: dict):
        assert payload["positive_points"] == [[0.5, 0.5], [0.6, 0.6]]
        assert payload["negative_points"] == [[0.1, 0.1]]
        assert payload["simplify"] == 0.4
        return {"polygon": [0.1, 0.1, 0.9, 0.1, 0.5, 0.9], "model": payload["model"]}, Path(payload["image_path"]).parent


def test_sam_preview_does_not_persist_shape(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    from yolo_factory.registry.database import create_registry, session_scope
    from yolo_factory.registry.models import Task
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        task = session.get(Task, "inspection")
        task.task_type = "segment"
        task.annotation_format = "yolo-seg"
    with TestClient(create_app(storage_root=storage, training_engine="simulation", sam_executor=PreviewSam())) as client:
        client.post("/api/annotation-images/sync", json={"task_id": "inspection"})
        response = client.post("/api/annotation-images/frame/sam/preview", json={"model": "sam2_t.pt", "positive_points": [[0.5, 0.5], [0.6, 0.6]], "negative_points": [[0.1, 0.1]], "simplify": 0.4})
        assert response.status_code == 200
        assert response.json()["polygon"] == [0.1, 0.1, 0.9, 0.1, 0.5, 0.9]
        assert client.get("/api/annotation-images/frame").json()["shapes"] == []
