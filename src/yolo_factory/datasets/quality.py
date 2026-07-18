from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class DatasetQualityReport:
    split_images: dict[str, int]
    split_instances: dict[str, int]
    class_instances: dict[str, dict[str, int]]
    empty_label_files: list[str]
    missing_label_files: list[str]
    imbalance_ratio: float | None
    blockers: list[str]
    warnings: list[str]

    def model_dump(self) -> dict:
        return asdict(self)


_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def analyze_dataset_quality(release_root: Path, *, class_names: list[str]) -> DatasetQualityReport:
    release_root = release_root.resolve()
    data_yaml = release_root / "data.yaml"
    if not data_yaml.is_file():
        return _empty_report(class_names, ["missing_data_yaml"])
    payload = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
    configured_root = _inside(release_root, release_root / str(payload.get("path", ".")))
    if configured_root is None:
        return _empty_report(class_names, ["dataset_path_outside_release"])

    split_images = {split: 0 for split in ("train", "val", "test")}
    split_instances = {split: 0 for split in split_images}
    class_instances = {name: {split: 0 for split in split_images} for name in class_names}
    empty_labels: list[str] = []
    missing_labels: list[str] = []
    blockers: list[str] = []
    malformed = False

    for split in split_images:
        references = payload.get(split)
        if references is None:
            continue
        if not isinstance(references, list):
            references = [references]
        images: list[Path] = []
        for reference in references:
            image_root = _inside(release_root, configured_root / str(reference))
            if image_root is None:
                blockers.append(f"{split}_path_outside_release")
                continue
            if image_root.is_file() and image_root.suffix.lower() == ".txt":
                for line in image_root.read_text(encoding="utf-8").splitlines():
                    candidate = _inside(release_root, configured_root / line.strip())
                    if candidate is not None and candidate.suffix.lower() in _IMAGE_SUFFIXES:
                        images.append(candidate)
            elif image_root.is_dir():
                images.extend(path for path in image_root.rglob("*") if path.suffix.lower() in _IMAGE_SUFFIXES)
        split_images[split] = len(images)
        for image in images:
            label = _label_path(image)
            if not label.is_file():
                missing_labels.append(image.relative_to(release_root).as_posix())
                continue
            lines = [line.strip() for line in label.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
            if not lines:
                empty_labels.append(label.relative_to(release_root).as_posix())
                continue
            for line in lines:
                fields = line.split()
                try:
                    class_id = int(fields[0])
                    if len(fields) < 3 or class_id < 0 or class_id >= len(class_names):
                        raise ValueError
                    [float(value) for value in fields[1:]]
                except (ValueError, IndexError):
                    malformed = True
                    continue
                split_instances[split] += 1
                class_instances[class_names[class_id]][split] += 1

    if split_images["train"] == 0:
        blockers.append("empty_train_split")
    if split_images["val"] == 0:
        blockers.append("empty_val_split")
    if missing_labels:
        blockers.append("missing_label_files")
    if malformed:
        blockers.append("malformed_or_out_of_range_labels")
    warnings = []
    if split_images["test"] == 0:
        warnings.append("empty_test_split")
    for name in class_names:
        if class_instances[name]["test"] < 10:
            warnings.append(f"test_class_evidence_low:{name}")
    totals = [sum(splits.values()) for splits in class_instances.values()]
    positive = [count for count in totals if count > 0]
    imbalance = max(positive) / min(positive) if len(positive) >= 2 else None
    return DatasetQualityReport(
        split_images=split_images,
        split_instances=split_instances,
        class_instances=class_instances,
        empty_label_files=sorted(empty_labels),
        missing_label_files=sorted(missing_labels),
        imbalance_ratio=imbalance,
        blockers=list(dict.fromkeys(blockers)),
        warnings=warnings,
    )


def _inside(root: Path, candidate: Path) -> Path | None:
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved


def _label_path(image: Path) -> Path:
    parts = list(image.parts)
    for index in range(len(parts) - 1, -1, -1):
        if parts[index] == "images":
            parts[index] = "labels"
            return Path(*parts).with_suffix(".txt")
    return image.with_suffix(".txt")


def _empty_report(class_names: list[str], blockers: list[str]) -> DatasetQualityReport:
    splits = {split: 0 for split in ("train", "val", "test")}
    return DatasetQualityReport(
        split_images=splits,
        split_instances=dict(splits),
        class_instances={name: dict(splits) for name in class_names},
        empty_label_files=[], missing_label_files=[], imbalance_ratio=None,
        blockers=blockers, warnings=[],
    )
