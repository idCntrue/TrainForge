from contextlib import contextmanager
from pathlib import Path

import yolo_factory.video.import_service as import_service
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import Task


def test_import_batches_duplicate_lookup_and_persistence(tmp_path: Path, monkeypatch) -> None:
    registry = create_registry(tmp_path / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="inspection", task_type="detect", annotation_format="yolo", classes_json='["defect"]'))
    sources = tmp_path / "sources"
    sources.mkdir()
    (sources / "camera-a.mp4").write_bytes(b"same-video")
    (sources / "camera-b.mov").write_bytes(b"same-video")
    calls = 0
    original_session_scope = import_service.session_scope

    @contextmanager
    def counting_session_scope(target_registry):
        nonlocal calls
        calls += 1
        with original_session_scope(target_registry) as session:
            yield session

    monkeypatch.setattr(import_service, "session_scope", counting_session_scope)

    result = import_service.import_video_collection(
        "inspection", "batch-001", sources, tmp_path / "storage", registry,
    )

    assert result.imported_count == 1
    assert result.duplicate_count == 1
    assert calls == 2
