import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml
from sqlalchemy import select

from yolo_factory.common.hashing import sha256_file
from yolo_factory.config.models import TaskConfig
from yolo_factory.integrations.datumaro import (
    validate_roboflow_detection_dataset,
)
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import AnnotationExport, Task


@dataclass(frozen=True)
class AnnotationImportResult:
    import_id: str
    sha256: str
    original_zip: Path
    extracted_root: Path
    sample_count: int


def _validate_member(member: zipfile.ZipInfo) -> None:
    path = PurePosixPath(member.filename.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe ZIP member: {member.filename}")


def _extract_safely(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            _validate_member(member)
        archive.extractall(destination)


def _load_classes(dataset_root: Path) -> list[str]:
    config_path = dataset_root / "data.yaml"
    if not config_path.is_file():
        raise ValueError("annotation export is missing data.yaml")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    names = config.get("names") if isinstance(config, dict) else None
    if isinstance(names, dict):
        try:
            names = [names[index] for index in range(len(names))]
        except (KeyError, TypeError):
            names = None
    if not isinstance(names, list) or not all(
        isinstance(name, str) for name in names
    ):
        raise ValueError("data.yaml must contain an ordered class list")
    return names


def _validate_segmentation_dataset(
    dataset_root: Path,
    class_count: int,
) -> int:
    image_paths = {
        path.relative_to(dataset_root).with_suffix("")
        for path in dataset_root.rglob("*")
        if path.is_file()
        and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
        and "images" in path.parts
    }
    if not image_paths:
        raise ValueError("annotation export contains no samples")

    label_files = sorted(
        path
        for path in dataset_root.rglob("*.txt")
        if "labels" in path.parts
    )
    for label_path in label_files:
        for line_number, line in enumerate(
            label_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            values = line.split()
            if len(values) < 7 or (len(values) - 1) % 2 != 0:
                raise ValueError(
                    f"invalid segmentation polygon: {label_path}:{line_number}"
                )
            try:
                class_id = int(values[0])
                coordinates = [float(value) for value in values[1:]]
            except ValueError as error:
                raise ValueError(
                    f"invalid segmentation polygon: {label_path}:{line_number}"
                ) from error
            if not 0 <= class_id < class_count:
                raise ValueError(f"invalid class ID: {class_id}")
            if any(coordinate < 0 or coordinate > 1 for coordinate in coordinates):
                raise ValueError("segmentation coordinates must be in [0, 1]")
    return len(image_paths)


def import_roboflow_export(
    zip_path: Path,
    task: TaskConfig,
    provider_project: str,
    provider_version: str,
    storage_root: Path,
    registry: Registry,
) -> AnnotationImportResult:
    zip_path = zip_path.resolve()
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"not a ZIP archive: {zip_path}")

    content_hash = sha256_file(zip_path)
    import_id = f"annotation-{task.task_id}-{provider_project}-{provider_version}"
    export_root = (
        storage_root
        / "annotation-exports"
        / task.task_id
        / provider_project
        / provider_version
    )
    original_zip = export_root / "original.zip"
    extracted_root = export_root / "extracted"

    with session_scope(registry) as session:
        if session.get(Task, task.task_id) is None:
            raise ValueError(f"unknown task: {task.task_id}")
        existing = session.scalar(
            select(AnnotationExport).where(
                AnnotationExport.task_id == task.task_id,
                AnnotationExport.provider_project == provider_project,
                AnnotationExport.provider_version == provider_version,
            )
        )
        if existing is not None:
            if existing.sha256 != content_hash:
                raise ValueError(
                    "provider project/version already exists with different content"
                )
            raise ValueError("annotation export already imported")

    temporary_root = export_root.with_name(export_root.name + ".tmp")
    if temporary_root.exists():
        shutil.rmtree(temporary_root)
    temporary_root.mkdir(parents=True)
    temporary_zip = temporary_root / "original.zip"
    temporary_extracted = temporary_root / "extracted"
    temporary_extracted.mkdir()

    try:
        shutil.copyfile(zip_path, temporary_zip)
        if sha256_file(temporary_zip) != content_hash:
            raise OSError("copied annotation ZIP hash mismatch")
        _extract_safely(temporary_zip, temporary_extracted)
        if _load_classes(temporary_extracted) != task.classes:
            raise ValueError("class order does not match task configuration")
        if task.task_type == "detect":
            sample_count = validate_roboflow_detection_dataset(
                temporary_extracted
            )
        else:
            sample_count = _validate_segmentation_dataset(
                temporary_extracted, len(task.classes)
            )
        export_root.parent.mkdir(parents=True, exist_ok=True)
        if export_root.exists():
            raise ValueError(f"annotation export path already exists: {export_root}")
        temporary_root.replace(export_root)
    except Exception:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise

    with session_scope(registry) as session:
        session.add(
            AnnotationExport(
                id=import_id,
                task_id=task.task_id,
                provider_project=provider_project,
                provider_version=provider_version,
                zip_path=original_zip.relative_to(storage_root).as_posix(),
                sha256=content_hash,
            )
        )

    return AnnotationImportResult(
        import_id=import_id,
        sha256=content_hash,
        original_zip=original_zip,
        extracted_root=extracted_root,
        sample_count=sample_count,
    )
