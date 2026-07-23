from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from yolo_factory.common.hashing import sha256_file
from yolo_factory.datasets.release import SEMANTIC_VERSION
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task


RELEASE_DIRECTORY = re.compile(r"^dataset-v(?P<version>.+)$")


class DatasetReconciliationError(ValueError):
    pass


@dataclass(frozen=True)
class DatasetReconciliationFinding:
    key: str
    release_id: str | None
    release_path: str
    task_id: str | None
    version: str | None
    database_exists: bool
    directory_exists: bool
    manifest_valid: bool
    checksums_valid: bool
    status: str
    message: str
    allowed_actions: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class _DirectoryInspection:
    release_path: str
    task_id: str | None
    version: str | None
    release_id: str | None
    manifest: dict
    manifest_valid: bool
    checksums_valid: bool
    status: str
    message: str
    provenance_valid: bool


def _managed_root(storage_root: Path) -> Path:
    return (storage_root / "dataset-releases").resolve()


def _managed_directory(storage_root: Path, release_path: str) -> Path:
    storage = storage_root.resolve()
    unresolved = storage / release_path
    for component in (unresolved, *unresolved.parents):
        if component == storage:
            break
        if component.exists() and component.is_symlink():
            raise DatasetReconciliationError("symbolic links are not allowed in managed dataset release paths")
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(_managed_root(storage_root))
    except ValueError as exc:
        raise DatasetReconciliationError("dataset release path is outside the managed release directory") from exc
    return candidate


def _read_manifest(directory: Path) -> tuple[dict, str | None]:
    path = directory / "manifest.yaml"
    if not path.is_file():
        return {}, "manifest.yaml is missing"
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        return {}, f"manifest.yaml cannot be parsed: {exc}"
    if not isinstance(payload, dict):
        return {}, "manifest.yaml must contain an object"
    required = {"annotation_import_id", "display_name", "task_id", "task_type", "version"}
    missing = sorted(required.difference(payload))
    if missing:
        return payload, f"manifest.yaml is missing: {', '.join(missing)}"
    return payload, None


def _verify_checksums(directory: Path) -> tuple[bool, str | None]:
    checksum_path = directory / "checksums.sha256"
    if not checksum_path.is_file():
        return False, "checksums.sha256 is missing"
    expected: dict[str, str] = {}
    try:
        lines = checksum_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        return False, f"checksums.sha256 cannot be read: {exc}"
    root = directory.resolve()
    for line in lines:
        parts = line.split("  ", 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            return False, "checksums.sha256 contains an invalid row"
        relative = Path(parts[1])
        if relative.is_absolute():
            return False, "checksums.sha256 contains an absolute path"
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            return False, "checksums.sha256 contains a path outside the release"
        if not path.is_file() or path.is_symlink():
            return False, f"checksum file is missing or unsafe: {relative.as_posix()}"
        expected[relative.as_posix()] = parts[0]
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != checksum_path
    }
    if set(expected) != actual_files:
        return False, "release files do not match the checksum index"
    for relative, digest in expected.items():
        if sha256_file(root / relative) != digest:
            return False, f"checksum mismatch: {relative}"
    return True, None


def _inspect_directory(registry: Registry, storage_root: Path, directory: Path) -> _DirectoryInspection:
    release_path = directory.relative_to(storage_root.resolve()).as_posix()
    task_id = directory.parent.name
    name_match = RELEASE_DIRECTORY.fullmatch(directory.name)
    version = name_match.group("version") if name_match else None
    manifest, manifest_error = _read_manifest(directory)
    if name_match is None or version is None or SEMANTIC_VERSION.fullmatch(version) is None:
        manifest_error = "release directory must be named dataset-v<semantic-version>"
    if not manifest_error and (manifest.get("task_id") != task_id or manifest.get("version") != version):
        manifest_error = "manifest task or version does not match the directory path"
    release_id = f"dataset-{task_id}-{version}" if version else None
    if manifest_error:
        return _DirectoryInspection(release_path, task_id, version, release_id, manifest, False, False, "invalid_manifest", manifest_error, False)
    checksums_valid, checksum_error = _verify_checksums(directory)
    if not checksums_valid:
        return _DirectoryInspection(release_path, task_id, version, release_id, manifest, True, False, "checksum_failed", checksum_error or "checksum validation failed", False)
    with session_scope(registry) as session:
        task = session.get(Task, task_id)
        annotation_export = session.get(AnnotationExport, str(manifest["annotation_import_id"]))
        provenance_valid = task is not None and annotation_export is not None and annotation_export.task_id == task_id
        if provenance_valid:
            try:
                classes = json.loads(task.classes_json)
                data = yaml.safe_load((directory / "data.yaml").read_text(encoding="utf-8")) or {}
                provenance_valid = data.get("names") == classes and manifest.get("task_type") == task.task_type
            except (OSError, UnicodeError, ValueError, yaml.YAMLError):
                provenance_valid = False
    if not provenance_valid:
        return _DirectoryInspection(release_path, task_id, version, release_id, manifest, True, True, "missing_provenance", "task, annotation export, or task contract is missing or inconsistent", False)
    return _DirectoryInspection(release_path, task_id, version, release_id, manifest, True, True, "orphan_directory", "validated release directory is not registered", True)


def scan_dataset_releases(registry: Registry, storage_root: Path) -> list[DatasetReconciliationFinding]:
    storage = storage_root.resolve()
    managed_root = _managed_root(storage_root)
    with session_scope(registry) as session:
        records = list(session.query(DatasetRelease).order_by(DatasetRelease.created_at.desc()))
    findings: list[DatasetReconciliationFinding] = []
    registered_paths = {record.release_path for record in records}
    for record in records:
        try:
            directory = _managed_directory(storage_root, record.release_path)
        except DatasetReconciliationError as exc:
            findings.append(DatasetReconciliationFinding(record.id, record.id, record.release_path, record.task_id, record.version, True, False, False, False, "conflict", str(exc), []))
            continue
        if not directory.is_dir():
            findings.append(DatasetReconciliationFinding(record.id, record.id, record.release_path, record.task_id, record.version, True, False, False, False, "missing_artifacts", "database record exists but the release directory is missing", []))
            continue
        inspection = _inspect_directory(registry, storage_root, directory)
        status = "healthy" if inspection.status == "orphan_directory" and inspection.release_id == record.id else inspection.status
        message = "database record and release directory are consistent" if status == "healthy" else inspection.message
        findings.append(DatasetReconciliationFinding(record.id, record.id, record.release_path, record.task_id, record.version, True, True, inspection.manifest_valid, inspection.checksums_valid, status, message, []))
    for directory in sorted(managed_root.glob("*/dataset-v*")):
        if not directory.is_dir() or directory.is_symlink():
            continue
        release_path = directory.relative_to(storage).as_posix()
        if release_path in registered_paths:
            continue
        inspection = _inspect_directory(registry, storage_root, directory)
        actions = ["register"] if inspection.status == "orphan_directory" and inspection.provenance_valid else []
        findings.append(DatasetReconciliationFinding(inspection.release_path, inspection.release_id, inspection.release_path, inspection.task_id, inspection.version, False, True, inspection.manifest_valid, inspection.checksums_valid, inspection.status, inspection.message, actions))
    return findings


def register_orphan_release(registry: Registry, storage_root: Path, release_path: str) -> DatasetRelease:
    directory = _managed_directory(storage_root, release_path)
    if not directory.is_dir():
        raise DatasetReconciliationError("dataset release directory does not exist")
    inspection = _inspect_directory(registry, storage_root, directory)
    if inspection.status != "orphan_directory" or not inspection.provenance_valid or not inspection.release_id or not inspection.task_id or not inspection.version:
        raise DatasetReconciliationError(inspection.message)
    with session_scope(registry) as session:
        if session.get(DatasetRelease, inspection.release_id) is not None:
            raise DatasetReconciliationError("dataset release is already registered")
        if session.query(DatasetRelease).filter(DatasetRelease.release_path == inspection.release_path).first() is not None:
            raise DatasetReconciliationError("dataset release path is already registered")
        release = DatasetRelease(
            id=inspection.release_id,
            task_id=inspection.task_id,
            annotation_export_id=str(inspection.manifest["annotation_import_id"]),
            display_name=str(inspection.manifest["display_name"]),
            version=inspection.version,
            release_path=inspection.release_path,
            status="published",
        )
        session.add(release)
    return release
