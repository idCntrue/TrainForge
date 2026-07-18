import re
import shutil
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

from yolo_factory.common.hashing import sha256_file
from yolo_factory.config.models import TaskConfig
from yolo_factory.datasets.validation import validate_dataset
from yolo_factory.datasets.split_planner import SampleRef, SplitRatios, plan_grouped_split
from yolo_factory.manifests.writer import write_manifest
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease

SEMANTIC_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class DvcClient(Protocol):
    def add(self, path: Path) -> None: ...


@dataclass(frozen=True)
class DatasetReleaseResult:
    release_id: str
    release_path: Path
    version: str
    status: str


def _write_data_yaml(path: Path, task: TaskConfig) -> None:
    dataset_root = path.parent
    train_path = "train/images"
    val_path = "val/images" if (dataset_root / "val" / "images").is_dir() else train_path
    test_path = "test/images" if (dataset_root / "test" / "images").is_dir() else val_path
    path.write_text(
        yaml.safe_dump(
            {
                "names": task.classes,
                "nc": len(task.classes),
                "path": ".",
                "test": test_path,
                "train": train_path,
                "val": val_path,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _write_checksums(root: Path) -> Path:
    checksum_path = root / "checksums.sha256"
    lines = [
        f"{sha256_file(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != checksum_path
    ]
    checksum_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checksum_path


def _set_status(
    registry: Registry,
    release_id: str,
    status: str,
) -> None:
    with session_scope(registry) as session:
        release = session.get(DatasetRelease, release_id)
        if release is None:
            raise ValueError(f"unknown dataset release: {release_id}")
        release.status = status


def release_dataset(
    task: TaskConfig,
    annotation_import_id: str,
    version: str,
    storage_root: Path,
    registry: Registry,
    dvc: DvcClient,
    *,
    display_name: str,
    split_ratios: dict[str, int] | None = None,
    split_seed: int = 42,
) -> DatasetReleaseResult:
    if SEMANTIC_VERSION.fullmatch(version) is None:
        raise ValueError(f"invalid semantic version: {version}")
    release_id = f"dataset-{task.task_id}-{version}"
    release_root = storage_root / "dataset-releases" / task.task_id
    release_path = release_root / f"dataset-v{version}"
    staging_path = release_root / f"dataset-v{version}.staging"

    with session_scope(registry) as session:
        annotation_export = session.get(AnnotationExport, annotation_import_id)
        if annotation_export is None or annotation_export.task_id != task.task_id:
            raise ValueError(f"unknown annotation import for task: {annotation_import_id}")
        existing = session.get(DatasetRelease, release_id)
        if existing is not None:
            if existing.status != "dvc_failed":
                raise ValueError(f"dataset release already exists: {release_id}")
            if not release_path.is_dir():
                raise ValueError("failed DVC release data is missing")
            try:
                dvc.add(release_path)
            except Exception:
                raise
            _set_status(registry, release_id, "published")
            return DatasetReleaseResult(release_id, release_path, version, "published")
        source_zip = storage_root / annotation_export.zip_path
        source_root = source_zip.parent / "extracted"

    if release_path.exists():
        raise ValueError(f"dataset release path already exists: {release_path}")
    if not source_root.is_dir():
        raise ValueError(f"annotation extraction is missing: {source_root}")
    shutil.rmtree(staging_path, ignore_errors=True)
    staging_path.mkdir(parents=True)
    try:
        source_index_path = source_root / "source-index.json"
        split_metadata: dict = {}
        if source_index_path.is_file():
            entries = json.loads(source_index_path.read_text(encoding="utf-8"))
            requested = split_ratios or {"train": 70, "val": 20, "test": 10}
            plan = plan_grouped_split(
                [SampleRef(entry["frame_id"], entry["source_group"]) for entry in entries],
                SplitRatios(requested["train"], requested["val"], requested["test"]),
                seed=split_seed,
            )
            for entry in entries:
                split = plan.split_for(entry["frame_id"])
                source_image = source_root / "train" / "images" / entry["image_name"]
                source_label = source_root / "train" / "labels" / f"{Path(entry['image_name']).stem}.txt"
                target_image = staging_path / split / "images" / source_image.name
                target_label = staging_path / split / "labels" / source_label.name
                target_image.parent.mkdir(parents=True, exist_ok=True)
                target_label.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_image, target_image)
                shutil.copy2(source_label, target_label)
            split_metadata = {
                "requested_ratios": plan.requested_ratios,
                "actual_ratios": plan.actual_ratios,
                "split_counts": plan.counts,
                "split_seed": split_seed,
                "grouping_strategy": "source-video",
            }
        else:
            for split in ("train", "val", "test"):
                source_split = source_root / split
                if source_split.exists():
                    shutil.copytree(source_split, staging_path / split)
        _write_data_yaml(staging_path / "data.yaml", task)
        report = validate_dataset(staging_path, task)
        if report.has_errors:
            codes = sorted({issue.code for issue in report.issues})
            raise ValueError(f"dataset validation failed: {', '.join(codes)}")
        write_manifest(
            staging_path / "manifest.yaml",
            {
                "annotation_import_id": annotation_import_id,
                "display_name": display_name,
                "sample_count": report.sample_count,
                "task_id": task.task_id,
                "task_type": task.task_type,
                "version": version,
                **split_metadata,
            },
        )
        _write_checksums(staging_path)
        release_root.mkdir(parents=True, exist_ok=True)
        staging_path.replace(release_path)
    except Exception:
        shutil.rmtree(staging_path, ignore_errors=True)
        raise

    with session_scope(registry) as session:
        session.add(
            DatasetRelease(
                id=release_id,
                task_id=task.task_id,
                annotation_export_id=annotation_import_id,
                display_name=display_name,
                version=version,
                release_path=release_path.relative_to(storage_root).as_posix(),
                status="dvc_failed",
            )
        )
    try:
        dvc.add(release_path)
    except Exception:
        raise
    _set_status(registry, release_id, "published")
    return DatasetReleaseResult(release_id, release_path, version, "published")
