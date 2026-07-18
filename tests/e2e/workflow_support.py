import json
import shutil
import zipfile
from pathlib import Path

import cv2
import numpy as np
import yaml
from PIL import Image
from sqlalchemy import select

from yolo_factory.annotations.import_service import import_roboflow_export
from yolo_factory.annotations.package_service import build_roboflow_package
from yolo_factory.config.models import TaskConfig
from yolo_factory.datasets.release import release_dataset
from yolo_factory.frames.extractor import extract_interval_frames
from yolo_factory.frames.selection import sync_selection
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import (
    FrameAsset,
    FrameBatch,
    Task,
    VideoAsset,
)
from yolo_factory.video.import_service import import_video_collection


class RecordingDvc:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def add(self, path: Path) -> None:
        assert path.is_dir()
        self.paths.append(path)


def _write_video(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 4.0, (32, 32)
    )
    assert writer.isOpened()
    for value in (20, 80, 140, 200):
        writer.write(np.full((32, 32, 3), value, dtype=np.uint8))
    writer.release()


def _write_export(root: Path, task: TaskConfig) -> Path:
    content = root / "export"
    for index, split in enumerate(("train", "val", "test")):
        image = content / split / "images" / f"sample-{split}.jpg"
        label = content / split / "labels" / f"sample-{split}.txt"
        image.parent.mkdir(parents=True)
        label.parent.mkdir(parents=True)
        Image.new("RGB", (24, 24), (40 + index * 60, 20, 20)).save(image)
        row = (
            "0 0.5 0.5 0.25 0.25"
            if task.task_type == "detect"
            else "0 0.1 0.1 0.8 0.1 0.8 0.8 0.1 0.8"
        )
        label.write_text(row + "\n", encoding="utf-8")
    (content / "data.yaml").write_text(
        yaml.safe_dump(
            {
                "train": "train/images",
                "val": "val/images",
                "test": "test/images",
                "nc": len(task.classes),
                "names": task.classes,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    archive_path = root / "roboflow.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(content.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(content).as_posix())
    return archive_path


def run_phase_one(tmp_path: Path, task_type: str) -> Path:
    task = TaskConfig(
        task_id=f"signal-light-{task_type}",
        task_type=task_type,
        classes=["red"],
        annotation_format="yolo-detect" if task_type == "detect" else "yolo-seg",
    )
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(
            Task(
                id=task.task_id,
                task_type=task.task_type,
                annotation_format=task.annotation_format,
                classes_json=json.dumps(task.classes),
            )
        )

    source_dir = tmp_path / "incoming"
    source_dir.mkdir()
    source_video = source_dir / "camera.avi"
    _write_video(source_video)
    imported = import_video_collection(
        task.task_id, "collection-001", source_dir, storage, registry
    )
    assert imported.imported_count == 1
    assert source_video.exists()
    with session_scope(registry) as session:
        video = session.scalar(select(VideoAsset))
        video_id = video.id
        stored_video = storage / video.stored_path

    extracted = extract_interval_frames(
        stored_video,
        tmp_path / "extracted",
        "collection-001",
        video_id,
        interval_seconds=0.25,
    )
    batch_dir = storage / "frame-batches" / task.task_id / "batch-001"
    candidates = batch_dir / "candidates"
    candidates.mkdir(parents=True)
    with session_scope(registry) as session:
        session.add(
            FrameBatch(
                id="batch-001",
                collection_id="collection-001",
                manifest_path=(batch_dir / "manifest.yaml").as_posix(),
            )
        )
        session.flush()
        for index, frame in enumerate(extracted):
            destination = candidates / frame.path.name
            shutil.copyfile(frame.path, destination)
            session.add(
                FrameAsset(
                    id=f"frame-{index}",
                    batch_id="batch-001",
                    video_id=video_id,
                    stored_path=destination.as_posix(),
                    sha256=frame.sha256,
                    timestamp_ms=frame.timestamp_ms,
                    frame_index=frame.frame_index,
                    status="candidate",
                )
            )
    selected = batch_dir / "selected"
    selected.mkdir()
    first = sorted(candidates.iterdir())[0]
    first.replace(selected / first.name)
    summary = sync_selection("batch-001", batch_dir, registry)
    assert summary.selected == 1
    package = build_roboflow_package(
        task.task_id,
        "batch-001",
        storage / "annotation-packages" / f"{task.task_id}.zip",
        registry,
    )
    assert package.image_count == 1

    annotation = import_roboflow_export(
        _write_export(tmp_path, task),
        task,
        provider_project=f"rf-{task_type}",
        provider_version="1",
        storage_root=storage,
        registry=registry,
    )
    dvc = RecordingDvc()
    release = release_dataset(
        task,
        annotation.import_id,
        "1.0.0",
        storage,
        registry,
        dvc,
        display_name=f"{task.task_id} dataset",
    )
    assert dvc.paths == [release.release_path]
    return release.release_path
