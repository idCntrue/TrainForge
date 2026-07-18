import json
from pathlib import Path

import yaml

from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import Task, VideoAsset
from yolo_factory.video.import_service import import_video_collection


def _seed_task(registry, task_id: str) -> None:
    with session_scope(registry) as session:
        session.add(
            Task(
                id=task_id,
                task_type="detect",
                annotation_format="yolo-detect",
                classes_json=json.dumps(["red"]),
            )
        )


def test_import_copies_video_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "incoming"
    source.mkdir()
    source_video = source / "camera 01.mp4"
    source_video.write_bytes(b"fake-video-one")
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    _seed_task(registry, "signal-light-detection")

    result = import_video_collection(
        task_id="signal-light-detection",
        collection_id="collection-20260713-001",
        source_dir=source,
        storage_root=storage,
        registry=registry,
    )

    assert source_video.exists()
    assert result.imported_count == 1
    assert result.duplicate_count == 0
    manifest = yaml.safe_load(result.manifest_path.read_text(encoding="utf-8"))
    stored_path = storage / manifest["videos"][0]["stored_path"]
    assert stored_path.read_bytes() == b"fake-video-one"
    assert not stored_path.with_suffix(stored_path.suffix + ".tmp").exists()


def test_import_skips_duplicate_content_within_task(tmp_path: Path) -> None:
    source = tmp_path / "incoming"
    source.mkdir()
    (source / "first.mp4").write_bytes(b"same-video")
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    _seed_task(registry, "signal-light-detection")

    first = import_video_collection(
        "signal-light-detection",
        "collection-20260713-001",
        source,
        storage,
        registry,
    )
    second = import_video_collection(
        "signal-light-detection",
        "collection-20260713-002",
        source,
        storage,
        registry,
    )

    assert first.imported_count == 1
    assert second.imported_count == 0
    assert second.duplicate_count == 1


def test_same_video_can_be_registered_for_another_task(tmp_path: Path) -> None:
    source = tmp_path / "incoming"
    source.mkdir()
    (source / "shared.mp4").write_bytes(b"shared-video")
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    _seed_task(registry, "signal-light-detection")
    _seed_task(registry, "smoke-detection")

    import_video_collection(
        "signal-light-detection",
        "collection-20260713-001",
        source,
        storage,
        registry,
    )
    result = import_video_collection(
        "smoke-detection",
        "collection-20260713-002",
        source,
        storage,
        registry,
    )

    assert result.imported_count == 1
    with session_scope(registry) as session:
        assert session.query(VideoAsset).count() == 2
