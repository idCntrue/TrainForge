import json
import time
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from yolo_factory.api import app as app_module
from yolo_factory.api.app import create_app
from yolo_factory.common.hashing import sha256_file
from yolo_factory.frames.extractor import ExtractedFrame
from yolo_factory.frames.video_append import VideoAppendResult, append_videos_to_batch
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import (
    AnnotationImageRecord,
    FrameAsset,
    FrameBatch,
    Task,
    VideoAsset,
    VideoCollection,
)


def _arrange(tmp_path: Path):
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    manifest = storage / "frame-batches" / "inspection" / "batch-existing" / "manifest.yaml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(yaml.safe_dump({
        "task_id": "inspection",
        "batch_id": "batch-existing",
        "source": "video-extraction",
        "interval": 2.0,
        "frames": [{"id": "frame-old", "video_id": "video-old"}],
    }), encoding="utf-8")
    old_image = manifest.parent / "selected" / "old.jpg"
    old_image.parent.mkdir()
    old_image.write_bytes(b"old-image")

    with session_scope(registry) as session:
        session.add(Task(id="inspection", task_type="detect", annotation_format="yolo-detect", classes_json='["defect"]'))
        session.add(VideoCollection(id="collection-existing", task_id="inspection"))
    with session_scope(registry) as session:
        session.add(VideoAsset(
            id="video-old", collection_id="collection-existing", original_name="old.mp4",
            stored_path="raw-videos/inspection/collection-existing/videos/old.mp4",
            sha256="a" * 64, size_bytes=10,
        ))
        session.add(FrameBatch(
            id="batch-existing", collection_id="collection-existing",
            manifest_path=manifest.relative_to(storage).as_posix(),
        ))
    with session_scope(registry) as session:
        session.add(FrameAsset(
            id="frame-old", batch_id="batch-existing", video_id="video-old",
            stored_path=old_image.relative_to(storage).as_posix(), sha256="b" * 64,
            timestamp_ms=0, frame_index=0, status="selected",
        ))
    with session_scope(registry) as session:
        session.add(AnnotationImageRecord(
            frame_id="frame-old", task_id="inspection",
            image_path=str(old_image.resolve()), width=100, height=100,
            status="reviewed", revision=3,
        ))
    source = tmp_path / "uploads"
    source.mkdir()
    (source / "new.mp4").write_bytes(b"new-video")
    return storage, registry, source, manifest


def test_appends_only_new_video_frames_and_preserves_existing_batch(tmp_path: Path) -> None:
    storage, registry, source, manifest = _arrange(tmp_path)

    def fake_extract(video_path, output_dir, collection_id, video_id, interval, quality):
        frame_path = output_dir / f"{video_id}.jpg"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        frame_path.write_bytes(b"new-frame")
        return [ExtractedFrame(
            path=frame_path,
            sha256=sha256_file(frame_path),
            source_video_sha256=sha256_file(video_path),
            timestamp_ms=1000,
            frame_index=10,
            width=640,
            height=480,
        )]

    result = append_videos_to_batch(
        "batch-existing", source, storage, registry,
        interval=1.0, quality=90, extractor=fake_extract,
    )

    assert result.imported_video_count == 1
    assert result.duplicate_video_count == 0
    assert result.created_frame_count == 1
    with session_scope(registry) as session:
        frames = list(session.query(FrameAsset).order_by(FrameAsset.id))
        old = session.get(FrameAsset, "frame-old")
        annotation = session.get(AnnotationImageRecord, "frame-old")
        videos = list(session.query(VideoAsset).order_by(VideoAsset.id))
        new = next(frame for frame in frames if frame.id != "frame-old")
        assert old.status == "selected"
        assert annotation.status == "reviewed"
        assert annotation.revision == 3
        assert new.status == "candidate"
        assert not Path(new.stored_path).is_absolute()
        assert new.storage_key == new.stored_path
        assert len(videos) == 2
        assert not Path(videos[-1].stored_path).is_absolute()

    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    assert payload["source"] == "video-extraction"
    assert payload["interval"] == 2.0
    assert payload["frames"] == [{"id": "frame-old", "video_id": "video-old"}]
    assert payload["appended_videos"][0]["original_name"] == "new.mp4"


def test_skips_task_duplicate_video_without_extracting_again(tmp_path: Path) -> None:
    storage, registry, source, _ = _arrange(tmp_path)
    calls = []

    def fake_extract(*args):
        calls.append(args)
        return []

    first = append_videos_to_batch(
        "batch-existing", source, storage, registry,
        interval=1.0, quality=90, extractor=fake_extract,
    )
    second = append_videos_to_batch(
        "batch-existing", source, storage, registry,
        interval=1.0, quality=90, extractor=fake_extract,
    )

    assert first.imported_video_count == 1
    assert second.imported_video_count == 0
    assert second.duplicate_video_count == 1
    assert len(calls) == 1


def test_batch_video_upload_runs_append_job_and_cleans_staging(
    tmp_path: Path, monkeypatch,
) -> None:
    storage, _, _, _ = _arrange(tmp_path)
    captured = {}

    def fake_append(batch_id, source_dir, storage_root, registry, **options):
        captured.update({
            "batch_id": batch_id,
            "filenames": sorted(path.name for path in source_dir.iterdir()),
            "storage_root": storage_root,
            **options,
        })
        assert source_dir.is_dir()
        return VideoAppendResult(batch_id, 1, 0, 3, 0)

    monkeypatch.setattr(app_module, "append_videos_to_batch", fake_append)
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.post(
            "/api/frame-batches/batch-existing/videos",
            data={"interval": "1.5", "quality": "88"},
            files=[("files", ("new.mp4", b"video", "video/mp4"))],
        )
        assert response.status_code == 202, response.text
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/api/jobs/{response.json()['job_id']}").json()
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)

    assert job["status"] == "completed", job
    assert job["payload"] == {
        "batch_id": "batch-existing",
        "imported_video_count": 1,
        "duplicate_video_count": 0,
        "created_frame_count": 3,
        "duplicate_frame_count": 0,
    }
    assert captured["batch_id"] == "batch-existing"
    assert captured["filenames"] == ["new.mp4"]
    assert captured["storage_root"] == storage.resolve()
    assert captured["interval"] == 1.5
    assert captured["quality"] == 88
    staging = storage / "imports" / "video-uploads"
    assert not staging.exists() or not list(staging.iterdir())
