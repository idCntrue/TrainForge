from pathlib import Path

import pytest
from pydantic import ValidationError

from yolo_factory.config.loader import load_system_config, load_task_config
from yolo_factory.config.models import TaskConfig


def test_rejects_relative_storage_root(tmp_path: Path) -> None:
    path = tmp_path / "system.yaml"
    path.write_text("storage_root: relative/path\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="absolute"):
        load_system_config(path)


def test_segment_requires_yolo_seg_format() -> None:
    with pytest.raises(ValidationError, match="yolo-seg"):
        TaskConfig(
            task_id="walkway-segmentation",
            task_type="segment",
            classes=["walkway"],
            annotation_format="yolo-detect",
        )


def test_detect_requires_yolo_detect_format() -> None:
    with pytest.raises(ValidationError, match="yolo-detect"):
        TaskConfig(
            task_id="signal-light-detection",
            task_type="detect",
            classes=["red"],
            annotation_format="yolo-seg",
        )


def test_rejects_duplicate_class_names() -> None:
    with pytest.raises(ValidationError, match="unique"):
        TaskConfig(
            task_id="signal-light-detection",
            task_type="detect",
            classes=["red", "red"],
            annotation_format="yolo-detect",
        )


def test_loads_ordered_task_classes(tmp_path: Path) -> None:
    path = tmp_path / "task.yaml"
    path.write_text(
        "\n".join(
            [
                "task_id: signal-light-detection",
                "task_type: detect",
                "classes:",
                "  - red",
                "  - yellow",
                "  - green",
                "annotation_format: yolo-detect",
            ]
        ),
        encoding="utf-8",
    )

    task = load_task_config(path)

    assert task.classes == ["red", "yellow", "green"]
