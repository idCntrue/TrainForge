import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

from yolo_factory.common.hashing import sha256_file
from yolo_factory.config.models import TaskConfig

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
SPLITS = ("train", "val", "test")


@dataclass(frozen=True)
class ValidationIssue:
    severity: Literal["error", "warning"]
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]
    sample_count: int
    class_counts: tuple[int, ...]
    report_path: Path
    statistics_path: Path

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


def _issue(code: str, path: Path, root: Path, message: str) -> ValidationIssue:
    return ValidationIssue(
        severity="error",
        code=code,
        path=path.relative_to(root).as_posix(),
        message=message,
    )


def _parse_class_id(
    value: str,
    path: Path,
    root: Path,
    class_count: int,
    issues: list[ValidationIssue],
) -> int | None:
    try:
        class_id = int(value)
    except ValueError:
        issues.append(_issue("invalid_class_id", path, root, value))
        return None
    if not 0 <= class_id < class_count:
        issues.append(_issue("class_overflow", path, root, value))
        return None
    return class_id


def _validate_label(
    path: Path,
    root: Path,
    task: TaskConfig,
    counts: list[int],
    issues: list[ValidationIssue],
) -> None:
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        values = line.split()
        if task.task_type == "detect" and len(values) != 5:
            issues.append(
                _issue(
                    "invalid_detection_row",
                    path,
                    root,
                    f"line {line_number} must contain 5 values",
                )
            )
            continue
        if task.task_type == "segment":
            coordinate_count = len(values) - 1
            if coordinate_count % 2:
                issues.append(
                    _issue(
                        "segmentation_odd_coordinates",
                        path,
                        root,
                        f"line {line_number} has an odd coordinate count",
                    )
                )
                continue
            if coordinate_count < 6:
                issues.append(
                    _issue(
                        "segmentation_too_few_points",
                        path,
                        root,
                        f"line {line_number} has fewer than 3 points",
                    )
                )
                continue

        class_id = _parse_class_id(
            values[0], path, root, len(task.classes), issues
        )
        try:
            coordinates = [float(value) for value in values[1:]]
        except ValueError:
            issues.append(
                _issue(
                    "invalid_coordinate",
                    path,
                    root,
                    f"line {line_number} contains a nonnumeric coordinate",
                )
            )
            continue
        if any(value < 0 or value > 1 for value in coordinates):
            issues.append(
                _issue(
                    "coordinate_out_of_range",
                    path,
                    root,
                    f"line {line_number} coordinates must be in [0, 1]",
                )
            )
        if class_id is not None:
            counts[class_id] += 1


def _write_outputs(
    root: Path,
    task: TaskConfig,
    issues: tuple[ValidationIssue, ...],
    sample_count: int,
    counts: list[int],
) -> tuple[Path, Path]:
    report_path = root / "validation-report.json"
    report_path.write_text(
        json.dumps(
            {
                "has_errors": any(issue.severity == "error" for issue in issues),
                "issues": [asdict(issue) for issue in issues],
                "sample_count": sample_count,
                "task_id": task.task_id,
                "task_type": task.task_type,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    statistics_path = root / "class-statistics.csv"
    with statistics_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["class_id", "class_name", "annotation_count"])
        for class_id, (class_name, count) in enumerate(zip(task.classes, counts)):
            writer.writerow([class_id, class_name, count])
    return report_path, statistics_path


def validate_dataset(root: Path, task: TaskConfig) -> ValidationReport:
    root = root.resolve()
    issues: list[ValidationIssue] = []
    counts = [0] * len(task.classes)
    hashes: dict[str, tuple[str, Path]] = {}
    sample_count = 0

    for split in SPLITS:
        images_root = root / split / "images"
        if not images_root.exists():
            continue
        for image_path in sorted(images_root.rglob("*")):
            if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            sample_count += 1
            try:
                with Image.open(image_path) as image:
                    image.verify()
            except (OSError, UnidentifiedImageError):
                issues.append(
                    _issue("corrupt_image", image_path, root, "image cannot be decoded")
                )

            digest = sha256_file(image_path)
            previous = hashes.get(digest)
            if previous is not None and previous[0] != split:
                issues.append(
                    _issue(
                        "split_hash_leakage",
                        image_path,
                        root,
                        f"duplicates {previous[1].relative_to(root).as_posix()}",
                    )
                )
            else:
                hashes[digest] = (split, image_path)

            relative = image_path.relative_to(images_root).with_suffix(".txt")
            label_path = root / split / "labels" / relative
            if not label_path.is_file():
                issues.append(
                    _issue("missing_label", image_path, root, "matching label is missing")
                )
                continue
            _validate_label(label_path, root, task, counts, issues)

    ordered_issues = tuple(sorted(issues, key=lambda item: (item.path, item.code)))
    report_path, statistics_path = _write_outputs(
        root, task, ordered_issues, sample_count, counts
    )
    return ValidationReport(
        issues=ordered_issues,
        sample_count=sample_count,
        class_counts=tuple(counts),
        report_path=report_path,
        statistics_path=statistics_path,
    )
