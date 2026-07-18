from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import Task, VideoAsset, VideoCollection


def test_registry_persists_task_and_collection(tmp_path: Path) -> None:
    registry = create_registry(tmp_path / "registry.db")

    with session_scope(registry) as session:
        session.add(
            Task(
                id="signal-light-detection",
                task_type="detect",
                annotation_format="yolo-detect",
                classes_json='["red","yellow","green"]',
            )
        )
        session.add(
            VideoCollection(
                id="collection-20260713-001",
                task_id="signal-light-detection",
            )
        )

    with session_scope(registry) as session:
        collection = session.get(VideoCollection, "collection-20260713-001")
        assert collection is not None
        assert collection.task_id == "signal-light-detection"


def test_registry_enforces_collection_foreign_key(tmp_path: Path) -> None:
    registry = create_registry(tmp_path / "registry.db")

    with pytest.raises(IntegrityError):
        with session_scope(registry) as session:
            session.add(
                VideoAsset(
                    id="video-deadbeef",
                    collection_id="missing-collection",
                    original_name="missing.mp4",
                    stored_path="raw-videos/missing.mp4",
                    sha256="0" * 64,
                    size_bytes=1,
                )
            )
