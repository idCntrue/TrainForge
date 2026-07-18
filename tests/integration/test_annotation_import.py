import json
import zipfile
from pathlib import Path

import pytest
import yaml
from PIL import Image

from yolo_factory.annotations.import_service import import_roboflow_export
from yolo_factory.config.models import TaskConfig
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import Task


def _build_export(
    root: Path,
    name: str,
    classes: list[str],
    label: str,
    unsafe_member: str | None = None,
) -> Path:
    content = root / f"{name}-content"
    images = content / "train" / "images"
    labels = content / "train" / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    Image.new("RGB", (32, 32), "white").save(images / "sample.jpg")
    (labels / "sample.txt").write_text(label + "\n", encoding="utf-8")
    (content / "data.yaml").write_text(
        yaml.safe_dump(
            {
                "train": "train/images",
                "val": "train/images",
                "nc": len(classes),
                "names": classes,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    archive_path = root / f"{name}.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(content.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(content).as_posix())
        if unsafe_member is not None:
            archive.writestr(unsafe_member, b"escape")
    return archive_path


def _seed_task(registry, task: TaskConfig) -> None:
    with session_scope(registry) as session:
        session.add(
            Task(
                id=task.task_id,
                task_type=task.task_type,
                annotation_format=task.annotation_format,
                classes_json=json.dumps(task.classes),
            )
        )


def test_imports_detection_export_with_datumaro(tmp_path: Path) -> None:
    task = TaskConfig(
        task_id="signal-light-detection",
        task_type="detect",
        classes=["red"],
        annotation_format="yolo-detect",
    )
    archive = _build_export(
        tmp_path,
        "detect",
        ["red"],
        "0 0.5 0.5 0.25 0.25",
    )
    registry = create_registry(tmp_path / "registry.db")
    _seed_task(registry, task)

    result = import_roboflow_export(
        archive,
        task,
        provider_project="signal-light",
        provider_version="1",
        storage_root=tmp_path / "storage",
        registry=registry,
    )

    assert result.sample_count == 1
    assert result.original_zip.read_bytes() == archive.read_bytes()
    assert (result.extracted_root / "data.yaml").exists()


def test_imports_segmentation_export_with_polygon_parser(tmp_path: Path) -> None:
    task = TaskConfig(
        task_id="signal-light-segmentation",
        task_type="segment",
        classes=["red"],
        annotation_format="yolo-seg",
    )
    archive = _build_export(
        tmp_path,
        "segment",
        ["red"],
        "0 0.1 0.1 0.8 0.1 0.8 0.8 0.1 0.8",
    )
    registry = create_registry(tmp_path / "registry.db")
    _seed_task(registry, task)

    result = import_roboflow_export(
        archive,
        task,
        provider_project="signal-light-seg",
        provider_version="1",
        storage_root=tmp_path / "storage",
        registry=registry,
    )

    assert result.sample_count == 1


def test_rejects_class_order_mismatch(tmp_path: Path) -> None:
    task = TaskConfig(
        task_id="signal-light-detection",
        task_type="detect",
        classes=["red", "green"],
        annotation_format="yolo-detect",
    )
    archive = _build_export(
        tmp_path,
        "wrong-classes",
        ["green", "red"],
        "0 0.5 0.5 0.25 0.25",
    )
    registry = create_registry(tmp_path / "registry.db")
    _seed_task(registry, task)

    with pytest.raises(ValueError, match="class order"):
        import_roboflow_export(
            archive,
            task,
            "signal-light",
            "1",
            tmp_path / "storage",
            registry,
        )


def test_rejects_zip_slip_member(tmp_path: Path) -> None:
    task = TaskConfig(
        task_id="signal-light-detection",
        task_type="detect",
        classes=["red"],
        annotation_format="yolo-detect",
    )
    archive = _build_export(
        tmp_path,
        "unsafe",
        ["red"],
        "0 0.5 0.5 0.25 0.25",
        unsafe_member="../escape.txt",
    )
    registry = create_registry(tmp_path / "registry.db")
    _seed_task(registry, task)

    with pytest.raises(ValueError, match="unsafe ZIP"):
        import_roboflow_export(
            archive,
            task,
            "signal-light",
            "1",
            tmp_path / "storage",
            registry,
        )
