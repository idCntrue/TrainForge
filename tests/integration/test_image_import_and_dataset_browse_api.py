import json
import io
import time
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from PIL import Image

from yolo_factory.api.app import create_app
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, FrameAsset, FrameBatch, Task, VideoAsset, VideoCollection


def _image_bytes(image_format: str = "JPEG") -> bytes:
    stream = io.BytesIO()
    Image.new("RGB", (64, 48), "white").save(stream, format=image_format)
    return stream.getvalue()


def test_uploads_images_into_annotation_queue_and_browses_release_images(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    release_root = storage / "dataset-releases" / "lights" / "v1"
    release_image = release_root / "images" / "train" / "sample.jpg"
    release_image.parent.mkdir(parents=True)
    release_image.write_bytes(b"release-image")
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json=json.dumps(["light"])))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="export-1", task_id="lights", provider_project="native", provider_version="1", zip_path="annotations.zip", sha256="a" * 64))
    with session_scope(registry) as session:
        session.add(DatasetRelease(id="release-1", task_id="lights", annotation_export_id="export-1", version="1.0.0", release_path=release_root.relative_to(storage).as_posix(), status="published"))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        uploaded = client.post(
            "/api/image-imports",
            data={"task_id": "lights", "batch_id": "uploaded-images"},
            files=[("files", ("one.jpg", b"one-image", "image/jpeg")), ("files", ("two.png", b"two-image", "image/png"))],
        )
        images = client.get("/api/dataset-releases/release-1/images")
        content = client.get("/api/dataset-releases/release-1/images/content", params={"path": "images/train/sample.jpg"})

    assert uploaded.status_code == 201
    assert uploaded.json()["imported_count"] == 2
    assert all(item["status"] == "selected" for item in uploaded.json()["frames"])
    assert images.json() == [{"path": "images/train/sample.jpg", "name": "sample.jpg", "size_bytes": 13}]
    assert content.content == b"release-image"


def test_paginates_frames_and_bulk_updates_all_matching_except_exclusions(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="inspection", task_type="detect", annotation_format="yolo-detect", classes_json=json.dumps(["defect"])))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        uploaded = client.post(
            "/api/image-imports",
            data={"task_id": "inspection", "batch_id": "bulk-images"},
            files=[("files", (f"image-{index}.jpg", f"image-{index}".encode(), "image/jpeg")) for index in range(3)],
        ).json()
        first_id = uploaded["frames"][0]["id"]

        page = client.get("/api/frame-batches/bulk-images/frames", params={"page": 2, "page_size": 1, "status": "selected"})
        assert page.status_code == 200
        assert page.json()["page"] == 2
        assert page.json()["total"] == 3
        assert len(page.json()["items"]) == 1
        assert page.json()["status_counts"]["selected"] == 3

        bulk = client.post("/api/frame-batches/bulk-images/bulk-selection", json={
            "selection": {"mode": "all_matching", "status": "selected", "search": "", "excluded_ids": [first_id]},
            "target_status": "rejected/other",
        })
        assert bulk.status_code == 202
        assert bulk.json()["affected_count"] == 2
        job_id = bulk.json()["job_id"]
        for _ in range(100):
            job = client.get(f"/api/jobs/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert job["status"] == "completed", job

        refreshed = client.get("/api/frame-batches/bulk-images/frames", params={"page": 1, "page_size": 10}).json()
        assert refreshed["status_counts"]["selected"] == 1
        assert refreshed["status_counts"]["rejected"] == 2


def test_appends_images_and_manages_seven_day_recycle_bin(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="inspection", task_type="detect", annotation_format="yolo-detect", classes_json='["defect"]'))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        created = client.post(
            "/api/image-imports",
            data={"task_id": "inspection", "batch_id": "append-images"},
            files=[("files", ("one.jpg", b"one", "image/jpeg"))],
        )
        appended = client.post(
            "/api/frame-batches/append-images/images",
            files=[
                ("files", ("duplicate.jpg", b"one", "image/jpeg")),
                ("files", ("two.jpg", b"two", "image/jpeg")),
            ],
        )
        manifest = json.loads((storage / "frame-batches/inspection/append-images/manifest.json").read_text(encoding="utf-8"))
        page = client.get("/api/frame-batches/append-images/frames").json()
        second_id = next(item["id"] for item in page["items"] if "two.jpg" in item["filename"])

        trashed = client.post(
            "/api/frame-batches/append-images/frames/trash",
            json={"mode": "explicit", "ids": [second_id], "request_id": "trash-request-1"},
        )
        active = client.get("/api/frame-batches/append-images/frames").json()
        recycle = client.get("/api/recycle-bin/frames").json()
        restored = client.post(
            "/api/recycle-bin/frames/restore",
            json={"ids": [second_id], "request_id": "restore-request-1"},
        )
        client.post(
            "/api/frame-batches/append-images/frames/trash",
            json={"mode": "explicit", "ids": [second_id], "request_id": "trash-request-2"},
        )
        purged = client.request(
            "DELETE", "/api/recycle-bin/frames",
            json={"ids": [second_id], "request_id": "purge-request-1", "confirm_count": 1},
        )

    assert created.status_code == 201
    assert appended.status_code == 201
    assert appended.json()["imported_count"] == 1
    assert appended.json()["skipped_count"] == 1
    assert len(manifest["frames"]) == 2
    assert any("two.jpg" in item["filename"] for item in manifest["frames"])
    assert trashed.status_code == 200
    assert active["total"] == 1
    assert recycle["total"] == 1
    assert recycle["items"][0]["batch_id"] == "append-images"
    assert restored.json()["affected_count"] == 1
    assert purged.status_code == 200
    assert purged.json()["deleted_count"] == 1


def test_appends_images_to_video_batch_without_rewriting_video_manifest(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    manifest_path = storage / "frame-batches" / "inspection" / "video-batch" / "manifest.yaml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(yaml.safe_dump({
        "task_id": "inspection",
        "batch_id": "video-batch",
        "source": "video-extraction",
        "interval": 1.0,
        "quality": 95,
        "frames": [{"id": "video-frame", "video_id": "source-video"}],
    }), encoding="utf-8")
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="inspection", task_type="detect", annotation_format="yolo-detect", classes_json='["defect"]'))
        session.add(VideoCollection(id="camera-import", task_id="inspection"))
    with session_scope(registry) as session:
        session.add(VideoAsset(id="source-video", collection_id="camera-import", original_name="camera.mp4", stored_path="raw/camera.mp4", sha256="a" * 64, size_bytes=100))
        session.add(FrameBatch(id="video-batch", collection_id="camera-import", manifest_path=manifest_path.relative_to(storage).as_posix()))
    with session_scope(registry) as session:
        session.add(FrameAsset(id="video-frame", batch_id="video-batch", video_id="source-video", stored_path="frames/video.jpg", sha256="b" * 64, timestamp_ms=1000, frame_index=0, status="selected"))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.post(
            "/api/frame-batches/video-batch/images",
            files=[("files", ("manual.jpg", b"manual-image", "image/jpeg"))],
        )

    assert response.status_code == 201, response.text
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["source"] == "video-extraction"
    assert manifest["interval"] == 1.0
    assert manifest["quality"] == 95
    assert manifest["frames"] == [{"id": "video-frame", "video_id": "source-video"}]
    assert manifest["appended_images"][0]["source"] == "manual-upload"
    with session_scope(registry) as session:
        original = session.get(FrameAsset, "video-frame")
        appended = next(frame for frame in session.query(FrameAsset).filter(FrameAsset.id != "video-frame"))
        assert original.video_id == "source-video"
        assert appended.video_id.startswith("image-source-")
        assert appended.video_id != original.video_id


def test_syncs_appended_storage_key_images_into_annotation_queue(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    original_image = storage / "frame-batches" / "inspection" / "video-batch" / "selected" / "original.jpg"
    original_image.parent.mkdir(parents=True)
    original_image.write_bytes(_image_bytes())
    manifest_path = original_image.parents[1] / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump({
        "task_id": "inspection",
        "batch_id": "video-batch",
        "source": "video-extraction",
        "frames": [{"id": "video-frame", "video_id": "source-video"}],
    }), encoding="utf-8")
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="inspection", task_type="detect", annotation_format="yolo-detect", classes_json='["defect"]'))
        session.add(VideoCollection(id="camera-import", task_id="inspection"))
    with session_scope(registry) as session:
        session.add(VideoAsset(id="source-video", collection_id="camera-import", original_name="camera.mp4", stored_path="raw/camera.mp4", sha256="a" * 64, size_bytes=100))
        session.add(FrameBatch(id="video-batch", collection_id="camera-import", manifest_path=manifest_path.relative_to(storage).as_posix()))
    with session_scope(registry) as session:
        session.add(FrameAsset(id="video-frame", batch_id="video-batch", video_id="source-video", stored_path=str(original_image.resolve()), sha256="b" * 64, timestamp_ms=1000, frame_index=0, status="selected"))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        appended = client.post(
            "/api/frame-batches/video-batch/images",
            files=[("files", ("追加图片.jpg", _image_bytes(), "image/jpeg"))],
        )
        synced = client.post("/api/annotation-images/sync", json={"task_id": "inspection"})
        queue = client.get("/api/annotation-images", params={"task_id": "inspection"})

        assert appended.status_code == 201, appended.text
        assert synced.status_code == 200, synced.text
        assert synced.json() == {"synced_count": 2, "total_count": 2}
        assert queue.json()["total"] == 2
        for item in queue.json()["items"]:
            content = client.get(f"/api/annotation-images/{item['frame_id']}/content")
            assert content.status_code == 200
            assert content.content == _image_bytes()
