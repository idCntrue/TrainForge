from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from yolo_factory.api.app import create_app
from yolo_factory.registry.database import session_scope
from yolo_factory.registry.models import (
    AnnotationImageRecord,
    FrameAsset,
    FrameBatch,
    Task,
    VideoAsset,
    VideoCollection,
)


class FakeDetector:
    def __init__(self) -> None:
        self.loads = 0

    def loaded_model_path(self) -> str | None:
        return "/fake/model.pt" if self.loads else None

    def detect(self, image_path, model_path, task_type, *, confidence=0.25, iou=0.7, imgsz=640):
        self.loads += 1
        return {
            "detections": [{
                "class_id": 0,
                "class_name": "red",
                "confidence": 0.91,
                "shape_type": "polygon",
                "coordinates": [0.4, 0.4, 0.6, 0.4, 0.6, 0.6, 0.4, 0.6],
            }],
            "names": {0: "red"},
            "speed": {},
        }


class FakeProcess:
    def __init__(self, output_path: Path, lines: list[dict]) -> None:
        output_path.write_text(
            "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines),
            encoding="utf-8",
        )

    def poll(self):
        return 0

    def terminate(self):
        return None

    def wait(self, timeout=None):
        return 0


def make_runner(lines: list[dict]):
    def factory(manifest_path: Path, output_path: Path):
        return FakeProcess(output_path, lines)

    return factory


def seed_batch(app, frame_count: int = 2) -> tuple[str, list[str], Path]:
    storage = Path(app.state.storage_root)
    image_dir = storage / "frames"
    image_dir.mkdir(parents=True, exist_ok=True)
    frame_ids: list[str] = []
    with session_scope(app.state.registry) as session:
        session.add(Task(id="task-1", task_type="segment", annotation_format="yolo-seg", classes_json=json.dumps(["red", "blue"])))
    with session_scope(app.state.registry) as session:
        session.add(VideoCollection(id="collection-1", task_id="task-1"))
    with session_scope(app.state.registry) as session:
        session.add(VideoAsset(id="video-1", collection_id="collection-1", original_name="a.mp4", stored_path="a.mp4", sha256="0" * 64, size_bytes=1))
    with session_scope(app.state.registry) as session:
        session.add(FrameBatch(id="batch-1", collection_id="collection-1", manifest_path="batch/manifest.json"))
    with session_scope(app.state.registry) as session:
        for index in range(frame_count):
            frame_id = f"frame-{index + 1}"
            image_path = image_dir / f"{frame_id}.jpg"
            Image.new("RGB", (32, 32), "white").save(image_path)
            session.add(FrameAsset(
                id=frame_id, batch_id="batch-1", video_id="video-1",
                stored_path=str(image_path), sha256="0" * 64, timestamp_ms=index * 1000,
                frame_index=index, status="selected", lifecycle_status="active",
            ))
            frame_ids.append(frame_id)
    with session_scope(app.state.registry) as session:
        for frame_id in frame_ids:
            session.add(AnnotationImageRecord(
                frame_id=frame_id, task_id="task-1", image_path=str(image_dir / f"{frame_id}.jpg"),
                width=32, height=32, status="pending", revision=0,
            ))
    return "batch-1", frame_ids, image_dir


def seed_model(app, path: Path) -> str:
    path.write_bytes(b"not-a-real-model")
    model = app.state.imported_model_repository.create(
        model_id="imported-model-test", name="测试模型", task_type="segment",
        artifact_format="pt", original_name="best.pt", artifact_path=str(path),
        size_bytes=path.stat().st_size, sha256="0" * 64, class_names=("red", "blue"),
    )
    return f"imported_model:{model.id}"


def wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish: {job}")


@pytest.fixture
def app(tmp_path: Path):
    detector = FakeDetector()
    app = create_app(
        storage_root=tmp_path / "storage",
        training_engine="simulation",
        detector_executor=detector,
    )
    app.state.fake_detector = detector
    return app


def test_batch_prelabel_creates_drafts_and_reports_adoption(app) -> None:
    batch_id, frame_ids, _ = seed_batch(app)
    model_source = seed_model(app, Path(app.state.storage_root) / "model.pt")
    app.state.prelabel_service._runner_factory = make_runner([
        {"status": "ok", "frame_id": frame_ids[0], "names": {0: "red", 1: "blue"}, "detections": [
            {"class_id": 0, "class_name": "red", "confidence": 0.8, "shape_type": "polygon", "coordinates": [0.1, 0.1, 0.9, 0.1, 0.9, 0.9]},
            {"class_id": 1, "class_name": "blue", "confidence": 0.6, "shape_type": "polygon", "coordinates": [0.2, 0.2, 0.8, 0.2, 0.8, 0.8]},
        ]},
        {"status": "ok", "frame_id": frame_ids[1], "names": {0: "red", 1: "blue"}, "detections": [
            {"class_id": 0, "class_name": "red", "confidence": 0.7, "shape_type": "polygon", "coordinates": [0.1, 0.1, 0.9, 0.1, 0.9, 0.9]},
        ]},
    ])
    client = TestClient(app)

    response = client.post(f"/api/frame-batches/{batch_id}/prelabel", json={"model_source": model_source, "confidence": 0.25})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["frames_total"] == 2
    job = wait_for_job(client, body["job_id"])
    assert job["status"] == "completed", job
    assert job["payload"]["shapes_created"] == 3

    image = client.get(f"/api/annotation-images/{frame_ids[0]}").json()
    assert image["status"] == "pending"
    assert len(image["shapes"]) == 2
    assert {shape["status"] for shape in image["shapes"]} == {"draft"}
    assert {shape["source"] for shape in image["shapes"]} == {"model"}
    assert all(shape["model_source"] == model_source for shape in image["shapes"])
    assert all(shape["confidence"] is not None for shape in image["shapes"])

    first_shape = image["shapes"][0]
    confirmed = client.post(
        f"/api/annotation-images/{frame_ids[0]}/shapes/{first_shape['id']}/status",
        json={"revision": image["revision"], "status": "confirmed"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "annotated"
    assert confirmed.json()["revision"] == image["revision"] + 1

    confirmed_image = confirmed.json()
    second_shape = next(shape for shape in confirmed_image["shapes"] if shape["id"] != first_shape["id"])
    rejected = client.post(
        f"/api/annotation-images/{frame_ids[0]}/shapes/{second_shape['id']}/status",
        json={"revision": confirmed_image["revision"], "status": "rejected"},
    )
    assert rejected.status_code == 200, rejected.text
    assert {shape["id"] for shape in rejected.json()["shapes"]} == {first_shape["id"]}

    stats = client.get("/api/prelabel-stats", params={"model_source": model_source}).json()
    assert stats["totals"] == {"created": 3, "draft": 1, "confirmed": 1, "rejected": 1}
    assert stats["adoption_rate"] == 0.5

    runs = client.get("/api/prelabel-runs").json()
    assert runs and runs[0]["status"] == "completed"
    assert runs[0]["shapes_created"] == 3
    assert runs[0]["unmapped_classes"] == []


def test_interactive_detect_adds_drafts_and_confirm_all(app) -> None:
    _, frame_ids, _ = seed_batch(app, frame_count=1)
    model_source = seed_model(app, Path(app.state.storage_root) / "model.pt")
    client = TestClient(app)

    image = client.get(f"/api/annotation-images/{frame_ids[0]}").json()
    response = client.post(
        f"/api/annotation-images/{frame_ids[0]}/detect",
        json={"revision": image["revision"], "model_source": model_source, "confidence": 0.3},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] == 1
    assert body["image"]["shapes"][0]["status"] == "draft"
    assert body["image"]["shapes"][0]["confidence"] == 0.91

    confirmed = client.post(
        f"/api/annotation-images/{frame_ids[0]}/drafts/confirm",
        json={"revision": body["image"]["revision"]},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "annotated"
    assert confirmed.json()["shapes"][0]["status"] == "confirmed"

    stats = client.get("/api/prelabel-stats").json()
    assert stats["totals"]["confirmed"] == 1


def test_prelabel_rejects_model_task_mismatch(app) -> None:
    batch_id, _, _ = seed_batch(app)
    model_source = seed_model(app, Path(app.state.storage_root) / "model.pt")
    app.state.imported_model_repository.create(
        model_id="imported-model-detect", name="检测模型", task_type="detect",
        artifact_format="pt", original_name="best.pt",
        artifact_path=str(Path(app.state.storage_root) / "model.pt"),
        size_bytes=1, sha256="0" * 64, class_names=("red",),
    )
    client = TestClient(app)
    response = client.post(
        f"/api/frame-batches/{batch_id}/prelabel",
        json={"model_source": "imported_model:imported-model-detect"},
    )
    assert response.status_code == 409
    assert "不一致" in response.json()["detail"]


def test_label_models_only_lists_matching_task_type(app) -> None:
    seed_batch(app)
    seed_model(app, Path(app.state.storage_root) / "model.pt")
    client = TestClient(app)
    models = client.get("/api/label-models", params={"task_id": "task-1"}).json()
    assert [model["model_source"] for model in models] == ["imported_model:imported-model-test"]
    assert models[0]["mapped_classes"] == 2
