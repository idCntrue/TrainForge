from pathlib import Path

from PIL import Image

from yolo_factory.config.models import TaskConfig
from yolo_factory.datasets.validation import validate_dataset


def _task(task_type: str = "detect") -> TaskConfig:
    return TaskConfig(
        task_id=f"signal-light-{task_type}",
        task_type=task_type,
        classes=["red", "green"],
        annotation_format="yolo-detect" if task_type == "detect" else "yolo-seg",
    )


def _sample(root: Path, split: str, name: str, label: str | None) -> Path:
    image = root / split / "images" / f"{name}.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), name if name in {"red", "green"} else "white").save(image)
    if label is not None:
        label_path = root / split / "labels" / f"{name}.txt"
        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.write_text(label + "\n", encoding="utf-8")
    return image


def _codes(root: Path, task: TaskConfig) -> set[str]:
    return {issue.code for issue in validate_dataset(root, task).issues}


def test_reports_corrupt_images_and_missing_labels(tmp_path: Path) -> None:
    image = _sample(tmp_path, "train", "red", None)
    image.write_bytes(b"broken")
    assert _codes(tmp_path, _task()) == {"corrupt_image", "missing_label"}


def test_reports_invalid_detection_rows(tmp_path: Path) -> None:
    _sample(tmp_path, "train", "red", "2 0.5 0.5 0.2 0.2")
    _sample(tmp_path, "val", "green", "0 1.2 0.5 0.2")
    assert _codes(tmp_path, _task()) == {
        "class_overflow",
        "invalid_detection_row",
    }


def test_reports_detection_coordinates_outside_unit_range(tmp_path: Path) -> None:
    _sample(tmp_path, "train", "red", "0 0.5 0.5 1.2 0.2")
    assert "coordinate_out_of_range" in _codes(tmp_path, _task())


def test_reports_invalid_segmentation_polygons(tmp_path: Path) -> None:
    _sample(tmp_path, "train", "red", "0 0.1 0.1 0.2 0.2")
    _sample(tmp_path, "val", "green", "0 0.1 0.1 0.2 0.2 0.3")
    assert _codes(tmp_path, _task("segment")) == {
        "segmentation_too_few_points",
        "segmentation_odd_coordinates",
    }


def test_reports_duplicate_image_hashes_across_splits(tmp_path: Path) -> None:
    first = _sample(tmp_path, "train", "red", "0 0.5 0.5 0.2 0.2")
    second = _sample(tmp_path, "test", "green", "1 0.5 0.5 0.2 0.2")
    second.write_bytes(first.read_bytes())
    report = validate_dataset(tmp_path, _task())
    assert "split_hash_leakage" in {issue.code for issue in report.issues}
    assert report.has_errors
    assert report.report_path.exists()
    assert report.statistics_path.exists()
