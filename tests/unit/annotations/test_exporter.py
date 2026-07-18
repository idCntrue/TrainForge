import json
from pathlib import Path

import pytest
from PIL import Image

from yolo_factory.annotations.exporter import export_reviewed_annotations
from yolo_factory.annotations.repository import AnnotationRepository
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import FrameAsset, FrameBatch, Task, VideoAsset, VideoCollection


def test_exports_reviewed_segment_annotations_as_deterministic_yolo(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    image_path = storage / "frames" / "selected" / "frame.jpg"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (100, 80), "white").save(image_path)
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="inspection", task_type="segment", annotation_format="yolo-seg", classes_json=json.dumps(["door"])))
    with session_scope(registry) as session:
        session.add(VideoCollection(id="collection", task_id="inspection"))
    with session_scope(registry) as session:
        session.add(VideoAsset(id="video", collection_id="collection", original_name="video.mp4", stored_path="raw/video.mp4", sha256="a" * 64, size_bytes=1))
        session.add(FrameBatch(id="batch", collection_id="collection", manifest_path="frames/manifest.yaml"))
    with session_scope(registry) as session:
        session.add(FrameAsset(id="frame", batch_id="batch", video_id="video", stored_path=str(image_path), sha256="b" * 64, timestamp_ms=0, frame_index=0, status="selected"))
    repository = AnnotationRepository(registry)
    repository.sync_selected_frames("inspection")
    _, annotated = repository.create_shape("frame", revision=0, class_id=0, class_name="door", shape_type="polygon", coordinates=[0.1, 0.1, 0.9, 0.1, 0.5, 0.9], source="manual")
    repository.set_status("frame", revision=annotated.revision, status="reviewed")

    result = export_reviewed_annotations("inspection", "native-1", storage, registry)

    label = result.extracted_root / "train" / "labels" / "frame.txt"
    assert label.read_text(encoding="utf-8") == "0 0.100000 0.100000 0.900000 0.100000 0.500000 0.900000\n"
    assert (result.extracted_root / "train" / "images" / "frame.jpg").is_file()
    assert result.sample_count == 1

    with pytest.raises(ValueError, match="already exists"):
        export_reviewed_annotations("inspection", "native-1", storage, registry)
