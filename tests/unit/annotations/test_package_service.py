import csv
import io
import json
import zipfile
from pathlib import Path

from yolo_factory.annotations.package_service import build_roboflow_package
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import (
    FrameAsset,
    FrameBatch,
    Task,
    VideoAsset,
    VideoCollection,
)


def _seed_selected_frame(registry, selected_path: Path, rejected_path: Path) -> None:
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
                original_name="camera.avi",
                stored_path="raw-videos/camera.avi",
                sha256="1" * 64,
                size_bytes=10,
            )
        )
        session.flush()
        session.add(
            FrameBatch(
                id="frames-20260713-001",
                collection_id="collection-20260713-001",
                manifest_path="frame-batches/manifest.yaml",
            )
        )
        session.flush()
        session.add_all(
            [
                FrameAsset(
                    id="frame-selected",
                    batch_id="frames-20260713-001",
                    video_id="video-test",
                    stored_path=selected_path.as_posix(),
                    sha256="2" * 64,
                    timestamp_ms=500,
                    frame_index=5,
                    status="selected",
                ),
                FrameAsset(
                    id="frame-rejected",
                    batch_id="frames-20260713-001",
                    video_id="video-test",
                    stored_path=rejected_path.as_posix(),
                    sha256="3" * 64,
                    timestamp_ms=1000,
                    frame_index=10,
                    status="rejected",
                    rejection_reason="blur",
                ),
            ]
        )


def test_builds_deterministic_package_with_source_map(tmp_path: Path) -> None:
    selected = tmp_path / "selected.jpg"
    rejected = tmp_path / "rejected.jpg"
    selected.write_bytes(b"selected-image")
    rejected.write_bytes(b"rejected-image")
    registry = create_registry(tmp_path / "registry.db")
    _seed_selected_frame(registry, selected, rejected)

    first = build_roboflow_package(
        "signal-light-detection",
        "frames-20260713-001",
        tmp_path / "first.zip",
        registry,
    )
    second = build_roboflow_package(
        "signal-light-detection",
        "frames-20260713-001",
        tmp_path / "second.zip",
        registry,
    )

    assert first.sha256 == second.sha256
    with zipfile.ZipFile(first.path) as archive:
        assert archive.namelist() == [
            "images/selected.jpg",
            "package-manifest.yaml",
            "source-map.csv",
        ]
        assert archive.read("images/selected.jpg") == b"selected-image"
        rows = list(
            csv.DictReader(
                io.StringIO(archive.read("source-map.csv").decode("utf-8"))
            )
        )
        assert rows == [
            {
                "image": "selected.jpg",
                "frame_id": "frame-selected",
                "source_video": "camera.avi",
                "source_video_id": "video-test",
                "timestamp_ms": "500",
                "frame_index": "5",
            }
        ]
