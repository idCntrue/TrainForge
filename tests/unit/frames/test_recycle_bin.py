from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from yolo_factory.frames.recycle_bin import FrameRecycleBin
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import (
    AnnotationImageRecord, AnnotationShapeRecord, FrameAsset, FrameBatch,
    Task, VideoAsset, VideoCollection,
)
from yolo_factory.storage.objects import LocalObjectStorage


def _recycle_bin(tmp_path: Path) -> tuple[FrameRecycleBin, object]:
    registry = create_registry(tmp_path / "registry" / "factory.db")
    image = tmp_path / "frame-batches" / "task" / "batch" / "selected" / "one.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"image")
    with session_scope(registry) as session:
        session.add(Task(id="task", task_type="detect", annotation_format="yolo-detect", classes_json='["sign"]'))
        session.add(VideoCollection(id="collection", task_id="task"))
    with session_scope(registry) as session:
        session.add(VideoAsset(id="video", collection_id="collection", original_name="one.jpg", stored_path=image.relative_to(tmp_path).as_posix(), sha256="a" * 64, size_bytes=5))
        session.add(FrameBatch(id="batch", collection_id="collection", manifest_path="manifest.json"))
    with session_scope(registry) as session:
        session.add(FrameAsset(id="frame", batch_id="batch", video_id="video", stored_path=image.relative_to(tmp_path).as_posix(), sha256="a" * 64, timestamp_ms=0, frame_index=0, status="selected", storage_key=image.relative_to(tmp_path).as_posix(), size_bytes=5))
    with session_scope(registry) as session:
        session.add(AnnotationImageRecord(frame_id="frame", task_id="task", image_path=image.relative_to(tmp_path).as_posix(), width=10, height=10, status="reviewed", revision=1))
    with session_scope(registry) as session:
        session.add(AnnotationShapeRecord(id="shape", frame_id="frame", class_id=0, class_name="sign", shape_type="box", coordinates_json="[0,0,1,1]", source="manual"))
    return FrameRecycleBin(registry, LocalObjectStorage(tmp_path), operations_root=tmp_path / "recycle-bin/operations"), registry


def test_trash_and_restore_preserve_annotations_and_previous_status(tmp_path: Path) -> None:
    recycle, registry = _recycle_bin(tmp_path)
    recycle.trash(["frame"])
    with session_scope(registry) as session:
        frame = session.get(FrameAsset, "frame")
        assert frame.lifecycle_status == "trashed"
        assert frame.pre_trash_status == "selected"
        assert session.get(AnnotationImageRecord, "frame") is not None

    recycle.restore(["frame"])
    with session_scope(registry) as session:
        frame = session.get(FrameAsset, "frame")
        assert frame.lifecycle_status == "active"
        assert frame.status == "selected"
        assert session.get(AnnotationShapeRecord, "shape") is not None


def test_permanent_purge_deletes_file_frame_source_and_annotations(tmp_path: Path) -> None:
    recycle, registry = _recycle_bin(tmp_path)
    recycle.trash(["frame"])
    result = recycle.purge(["frame"])

    assert result.deleted_count == 1
    assert result.released_bytes == 5
    with session_scope(registry) as session:
        assert session.get(FrameAsset, "frame") is None
        assert session.get(VideoAsset, "video") is None
        assert session.get(AnnotationImageRecord, "frame") is None
        assert session.get(AnnotationShapeRecord, "shape") is None
    assert not (tmp_path / "frame-batches/task/batch/selected/one.jpg").exists()


def test_purge_requires_trashed_frame_and_expiry_respects_boundary(tmp_path: Path) -> None:
    recycle, registry = _recycle_bin(tmp_path)
    with pytest.raises(ValueError, match="recycle bin"):
        recycle.purge(["frame"])
    recycle.trash(["frame"])
    with session_scope(registry) as session:
        session.get(FrameAsset, "frame").purge_after = datetime.now(timezone.utc) + timedelta(days=1)
    assert recycle.purge_expired().deleted_count == 0
    with session_scope(registry) as session:
        session.get(FrameAsset, "frame").purge_after = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert recycle.purge_expired().deleted_count == 1


def test_purge_accepts_legacy_absolute_paths_inside_storage_root(tmp_path: Path) -> None:
    recycle, registry = _recycle_bin(tmp_path)
    image = tmp_path / "frame-batches/task/batch/selected/one.jpg"
    with session_scope(registry) as session:
        frame = session.get(FrameAsset, "frame")
        frame.storage_key = image.resolve().as_posix()
        frame.stored_path = image.resolve().as_posix()

    recycle.trash(["frame"])
    result = recycle.purge(["frame"])

    assert result.failed_keys == ()
    assert not image.exists()


def test_repeated_request_id_returns_the_original_mutation_result(tmp_path: Path) -> None:
    recycle, _ = _recycle_bin(tmp_path)

    assert recycle.trash(["frame"], request_id="trash-request-1") == 1
    assert recycle.trash(["frame"], request_id="trash-request-1") == 1
    first = recycle.purge(["frame"], request_id="purge-request-1")
    repeated = recycle.purge(["frame"], request_id="purge-request-1")

    assert repeated == first
