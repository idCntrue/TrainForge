import json
import os
from io import BytesIO
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from yolo_factory.api.app import create_app
from yolo_factory.integrations.dvc import DvcAdapter
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationImageRecord, AnnotationShapeRecord, FrameAsset, FrameBatch, Task, VideoAsset, VideoCollection


def _storage(tmp_path: Path) -> Path:
    storage = tmp_path / "storage"
    image = storage / "frames" / "selected" / "frame.jpg"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (320, 240), "white").save(image)
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="inspection", task_type="detect", annotation_format="yolo-detect", classes_json=json.dumps(["door"])))
    with session_scope(registry) as session:
        session.add(VideoCollection(id="collection", task_id="inspection"))
    with session_scope(registry) as session:
        session.add(VideoAsset(id="video", collection_id="collection", original_name="video.mp4", stored_path="raw/video.mp4", sha256="a" * 64, size_bytes=1))
        session.add(FrameBatch(id="batch", collection_id="collection", manifest_path="frames/manifest.yaml"))
    with session_scope(registry) as session:
        session.add(FrameAsset(id="frame", batch_id="batch", video_id="video", stored_path=str(image), sha256="b" * 64, timestamp_ms=0, frame_index=0, status="selected"))
    return storage


def test_native_annotation_crud_status_and_export(tmp_path: Path, monkeypatch) -> None:
    storage = _storage(tmp_path)
    monkeypatch.setattr(DvcAdapter, "add", lambda self, path: None)
    with TestClient(create_app(storage_root=storage, task_config_dir=tmp_path / "empty-task-configs", training_engine="simulation")) as client:
        queue = client.post("/api/annotation-images/sync", json={"task_id": "inspection"})
        assert queue.status_code == 200
        assert queue.json() == {"synced_count": 1, "total_count": 1}

        created = client.post("/api/annotation-images/frame/shapes", json={"revision": 0, "class_id": 0, "class_name": "door", "shape_type": "box", "coordinates": [0.5, 0.5, 0.2, 0.2], "source": "manual"})
        assert created.status_code == 201
        assert created.json()["revision"] == 1

        conflict = client.delete(f"/api/annotation-images/frame/shapes/{created.json()['shapes'][0]['id']}", params={"revision": 0})
        assert conflict.status_code == 409

        reviewed = client.post("/api/annotation-images/frame/status", json={"revision": 1, "status": "reviewed"})
        assert reviewed.json()["status"] == "reviewed"
        exported = client.post("/api/annotation-exports/native", json={"task_id": "inspection", "export_name": "native-1"})
        assert exported.status_code == 201
        assert exported.json()["sample_count"] == 1

        released = client.post("/api/dataset-releases", json={
            "task_id": "inspection",
            "annotation_import_id": exported.json()["export_id"],
            "display_name": "巡检数据集",
            "version": "1.0.0",
            "split_ratios": {"train": 100, "val": 0, "test": 0},
            "split_seed": 42,
        })
        assert released.status_code == 200, released.text
        releases = client.get("/api/dataset-releases").json()
        assert releases[0]["display_name"] == "巡检数据集"
        data_yaml = storage / released.json()["release_path"] / "data.yaml"
        assert "- door" in data_yaml.read_text(encoding="utf-8")

        content = client.get("/api/annotation-images/frame/content")
        assert content.status_code == 200


def _paginated_storage(tmp_path: Path) -> Path:
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="inspection", task_type="detect", annotation_format="yolo-detect", classes_json=json.dumps(["door"])))
        session.add(VideoCollection(id="collection", task_id="inspection"))
    with session_scope(registry) as session:
        session.add(VideoAsset(id="video", collection_id="collection", original_name="video.mp4", stored_path="raw/video.mp4", sha256="a" * 64, size_bytes=1))
        session.add(FrameBatch(id="batch", collection_id="collection", manifest_path="frames/manifest.yaml"))
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    statuses = ["pending", "annotated", "reviewed", "pending", "reviewed"]
    image_paths: list[Path] = []
    with session_scope(registry) as session:
        for index, status in enumerate(statuses):
            frame_id = f"frame-{index}"
            image_path = storage / "frames" / f"{frame_id}.jpg"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (640, 480), "white").save(image_path)
            image_paths.append(image_path)
            session.add(FrameAsset(id=frame_id, batch_id="batch", video_id="video", stored_path=str(image_path), sha256=f"{index:064d}", timestamp_ms=index, frame_index=index, status="selected"))
    with session_scope(registry) as session:
        for index, status in enumerate(statuses):
            frame_id = f"frame-{index}"
            image_path = image_paths[index]
            session.add(AnnotationImageRecord(frame_id=frame_id, task_id="inspection", image_path=str(image_path), width=640, height=480, status=status, revision=1 if status != "pending" else 0, created_at=base_time + timedelta(seconds=index)))
    with session_scope(registry) as session:
        for index, status in enumerate(statuses):
            if status != "pending":
                session.add(AnnotationShapeRecord(id=f"shape-{index}", frame_id=f"frame-{index}", class_id=0, class_name="door", shape_type="box", coordinates_json=json.dumps([0.5, 0.5, 0.2, 0.2]), source="manual", created_at=base_time + timedelta(seconds=index)))
    return storage


def test_lists_annotation_queue_as_server_paginated_summaries(tmp_path: Path) -> None:
    storage = _paginated_storage(tmp_path)

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.get("/api/annotation-images", params={"task_id": "inspection", "page": 2, "page_size": 2})

    assert response.status_code == 200
    payload = response.json()
    assert [item["frame_id"] for item in payload["items"]] == ["frame-2", "frame-3"]
    assert payload["page"] == 2
    assert payload["page_size"] == 2
    assert payload["total"] == 5
    assert payload["status_counts"] == {"pending": 2, "annotated": 1, "reviewed": 2}
    assert payload["items"][0]["shape_count"] == 1
    assert "shapes" not in payload["items"][0]
    assert "classes" not in payload["items"][0]


def test_annotation_queue_total_respects_status_filter_but_counts_cover_task(tmp_path: Path) -> None:
    storage = _paginated_storage(tmp_path)

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.get("/api/annotation-images", params={"task_id": "inspection", "status": "reviewed", "page": 1, "page_size": 1})

    payload = response.json()
    assert payload["total"] == 2
    assert len(payload["items"]) == 1
    assert payload["status_counts"] == {"pending": 2, "annotated": 1, "reviewed": 2}


def test_annotation_thumbnail_is_bounded_cached_and_storage_scoped(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        client.post("/api/annotation-images/sync", json={"task_id": "inspection"})

        first = client.get("/api/annotation-images/frame/thumbnail")
        assert first.status_code == 200
        assert first.headers["content-type"] == "image/jpeg"
        with Image.open(BytesIO(first.content)) as thumbnail:
            assert thumbnail.size[0] <= 160
            assert thumbnail.size[1] <= 120

        cache_files = list((storage / "thumbnails" / "annotations").glob("*.jpg"))
        assert len(cache_files) == 1
        marker = 1_700_000_000_000_000_000
        os.utime(cache_files[0], ns=(marker, marker))
        second = client.get("/api/annotation-images/frame/thumbnail")
        assert second.status_code == 200
        assert cache_files[0].stat().st_mtime_ns == marker

        outside = tmp_path / "outside.jpg"
        Image.new("RGB", (320, 240), "black").save(outside)
        registry = create_registry(storage / "registry" / "factory.db")
        with session_scope(registry) as session:
            session.get(AnnotationImageRecord, "frame").image_path = str(outside)

        forbidden = client.get("/api/annotation-images/frame/thumbnail")
        assert forbidden.status_code == 403
