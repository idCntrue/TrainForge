import json
from pathlib import Path

import pytest
from PIL import Image

from yolo_factory.annotations.repository import AnnotationConflict, AnnotationRepository, InvalidAnnotationTransition
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import FrameAsset, FrameBatch, Task, VideoAsset, VideoCollection


def _repository(tmp_path: Path, *, task_type: str = "segment", structured_metadata: bool = False) -> AnnotationRepository:
    image = tmp_path / "selected" / "frame.jpg"
    image.parent.mkdir()
    Image.new("RGB", (640, 480), "white").save(image)
    registry = create_registry(tmp_path / "factory.db")
    with session_scope(registry) as session:
        classes_json = json.dumps({"classes": ["door", "sign"], "display_names": {"door": "门"}}) if structured_metadata else json.dumps(["door", "sign"])
        session.add(Task(id="inspection", task_type=task_type, annotation_format="yolo-seg" if task_type == "segment" else "yolo-detect", classes_json=classes_json))
    with session_scope(registry) as session:
        session.add(VideoCollection(id="collection", task_id="inspection"))
    with session_scope(registry) as session:
        session.add(VideoAsset(id="video", collection_id="collection", original_name="source.mp4", stored_path="raw/source.mp4", sha256="a" * 64, size_bytes=10))
        session.add(FrameBatch(id="batch", collection_id="collection", manifest_path="batch/manifest.yaml"))
    with session_scope(registry) as session:
        session.add(FrameAsset(id="frame-selected", batch_id="batch", video_id="video", stored_path=str(image), sha256="b" * 64, timestamp_ms=0, frame_index=0, status="selected"))
        session.add(FrameAsset(id="frame-rejected", batch_id="batch", video_id="video", stored_path=str(tmp_path / "rejected.jpg"), sha256="c" * 64, timestamp_ms=1, frame_index=1, status="rejected"))
    return AnnotationRepository(registry)


def test_registers_only_selected_frames_and_persists_shapes(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    queue = repository.sync_selected_frames("inspection")
    assert [image.frame_id for image in queue] == ["frame-selected"]
    assert queue[0].width == 640
    assert queue[0].height == 480

    shape, image = repository.create_shape("frame-selected", revision=0, class_id=0, class_name="door", shape_type="polygon", coordinates=[0.1, 0.1, 0.8, 0.1, 0.5, 0.8], source="manual")
    assert shape.class_name == "door"
    assert image.revision == 1
    assert image.status == "annotated"
    assert repository.get_required("frame-selected").shapes == (shape,)


def test_rejects_stale_revision_and_locks_reviewed_images(tmp_path: Path) -> None:
    repository = _repository(tmp_path, task_type="detect")
    repository.sync_selected_frames("inspection")
    _, image = repository.create_shape("frame-selected", revision=0, class_id=0, class_name="door", shape_type="box", coordinates=[0.5, 0.5, 0.2, 0.2], source="manual")
    with pytest.raises(AnnotationConflict):
        repository.create_shape("frame-selected", revision=0, class_id=0, class_name="door", shape_type="box", coordinates=[0.4, 0.4, 0.2, 0.2], source="manual")

    reviewed = repository.set_status("frame-selected", revision=image.revision, status="reviewed")
    with pytest.raises(InvalidAnnotationTransition, match="read-only"):
        repository.delete_shape("frame-selected", reviewed.shapes[0].id, revision=reviewed.revision)

    returned = repository.set_status("frame-selected", revision=reviewed.revision, status="annotated")
    deleted = repository.delete_shape("frame-selected", returned.shapes[0].id, revision=returned.revision)
    assert deleted.status == "pending"
    assert deleted.shapes == ()


def test_structured_task_metadata_exposes_real_classes_to_annotation_operations(tmp_path: Path) -> None:
    repository = _repository(tmp_path, structured_metadata=True)

    queue = repository.sync_selected_frames("inspection")
    shape, image = repository.create_shape("frame-selected", revision=0, class_id=0, class_name="door", shape_type="polygon", coordinates=[0.1, 0.1, 0.8, 0.1, 0.5, 0.8], source="manual")

    assert queue[0].classes == ("door", "sign")
    assert shape.class_name == "door"
    assert image.classes == ("door", "sign")
