import json
from pathlib import Path

import pytest
import yaml

from yolo_factory.frames.selection import sync_selection
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import (
    FrameAsset,
    FrameBatch,
    Task,
    VideoAsset,
    VideoCollection,
)


def _seed_frames(registry, batch_dir: Path) -> None:
    with session_scope(registry) as session:
        session.add(
            Task(
                id="signal-light-detection",
                task_type="detect",
                annotation_format="yolo-detect",
                classes_json=json.dumps(["red"]),
            )
        )
        session.flush()
        session.add(
            VideoCollection(
                id="collection-20260713-001",
                task_id="signal-light-detection",
            )
        )
        session.flush()
        session.add(
            VideoAsset(
                id="video-test",
                collection_id="collection-20260713-001",
                original_name="source.avi",
                stored_path="raw-videos/source.avi",
                sha256="1" * 64,
                size_bytes=10,
            )
        )
        session.flush()
        session.add(
            FrameBatch(
                id="frames-20260713-001",
                collection_id="collection-20260713-001",
                manifest_path=(batch_dir / "manifest.yaml").as_posix(),
            )
        )
        session.flush()
        session.add_all(
            [
                FrameAsset(
                    id="frame-selected",
                    batch_id="frames-20260713-001",
                    video_id="video-test",
                    stored_path=(batch_dir / "candidates" / "selected.jpg").as_posix(),
                    sha256="2" * 64,
                    timestamp_ms=0,
                    frame_index=0,
                ),
                FrameAsset(
                    id="frame-rejected",
                    batch_id="frames-20260713-001",
                    video_id="video-test",
                    stored_path=(batch_dir / "candidates" / "rejected.jpg").as_posix(),
                    sha256="3" * 64,
                    timestamp_ms=500,
                    frame_index=5,
                ),
            ]
        )


def test_syncs_selected_and_rejected_folders(tmp_path: Path) -> None:
    batch_dir = tmp_path / "frames-20260713-001"
    selected = batch_dir / "selected"
    rejected = batch_dir / "rejected" / "blur"
    selected.mkdir(parents=True)
    rejected.mkdir(parents=True)
    (selected / "selected.jpg").write_bytes(b"selected")
    (rejected / "rejected.jpg").write_bytes(b"rejected")
    registry = create_registry(tmp_path / "registry.db")
    _seed_frames(registry, batch_dir)

    summary = sync_selection(
        batch_id="frames-20260713-001",
        batch_dir=batch_dir,
        registry=registry,
    )

    assert summary.selected == 1
    assert summary.rejected == 1
    with session_scope(registry) as session:
        selected_frame = session.get(FrameAsset, "frame-selected")
        rejected_frame = session.get(FrameAsset, "frame-rejected")
        assert selected_frame.status == "selected"
        assert selected_frame.rejection_reason is None
        assert rejected_frame.status == "rejected"
        assert rejected_frame.rejection_reason == "blur"
    manifest = yaml.safe_load(
        (batch_dir / "selection-manifest.yaml").read_text(encoding="utf-8")
    )
    assert [item["id"] for item in manifest["frames"]] == [
        "frame-rejected",
        "frame-selected",
    ]


def test_rejects_unregistered_file(tmp_path: Path) -> None:
    batch_dir = tmp_path / "frames-20260713-001"
    selected = batch_dir / "selected"
    selected.mkdir(parents=True)
    (selected / "unknown.jpg").write_bytes(b"unknown")
    registry = create_registry(tmp_path / "registry.db")
    _seed_frames(registry, batch_dir)

    with pytest.raises(ValueError, match="unregistered"):
        sync_selection(
            batch_id="frames-20260713-001",
            batch_dir=batch_dir,
            registry=registry,
        )


def test_sync_ignores_trashed_registered_frames(tmp_path: Path) -> None:
    batch_dir = tmp_path / "frames-20260713-001"
    selected = batch_dir / "selected"
    selected.mkdir(parents=True)
    (selected / "selected.jpg").write_bytes(b"selected")
    registry = create_registry(tmp_path / "registry.db")
    _seed_frames(registry, batch_dir)
    with session_scope(registry) as session:
        frame = session.get(FrameAsset, "frame-selected")
        frame.lifecycle_status = "trashed"

    summary = sync_selection("frames-20260713-001", batch_dir, registry)

    assert summary.selected == 0
    manifest = yaml.safe_load((batch_dir / "selection-manifest.yaml").read_text(encoding="utf-8"))
    assert "frame-selected" not in [item["id"] for item in manifest["frames"]]
