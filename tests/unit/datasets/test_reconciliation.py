import json
import shutil
from pathlib import Path

from PIL import Image
from sqlalchemy import delete

from yolo_factory.config.models import TaskConfig
from yolo_factory.datasets.reconciliation import register_orphan_release, scan_dataset_releases
from yolo_factory.datasets.release import release_dataset
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task


class NoopDvc:
    def add(self, path: Path) -> None:
        assert path.is_dir()


def test_scan_does_not_create_the_managed_release_directory(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    registry = create_registry(tmp_path / "registry.db")

    assert scan_dataset_releases(registry, storage) == []
    assert not (storage / "dataset-releases").exists()


def _release(tmp_path: Path, version: str = "1.0.0"):
    storage = tmp_path / "storage"
    extracted = storage / "annotation-exports" / "lights" / "native" / "1" / "extracted"
    image_path = extracted / "train" / "images" / "sample.jpg"
    label_path = extracted / "train" / "labels" / "sample.txt"
    image_path.parent.mkdir(parents=True)
    label_path.parent.mkdir(parents=True)
    Image.new("RGB", (16, 16), (255, 0, 0)).save(image_path)
    label_path.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    registry = create_registry(tmp_path / "registry.db")
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json=json.dumps(["red"])))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="annotation-lights-native-1", task_id="lights", provider_project="native", provider_version="1", zip_path="annotation-exports/lights/native/1/original.zip", sha256="a" * 64))
    result = release_dataset(
        TaskConfig(task_id="lights", task_type="detect", classes=["red"], annotation_format="yolo-detect"),
        "annotation-lights-native-1",
        version,
        storage,
        registry,
        NoopDvc(),
        display_name="Lights dataset",
    )
    return registry, storage, result


def test_scan_classifies_healthy_and_missing_release(tmp_path: Path) -> None:
    registry, storage, result = _release(tmp_path)
    healthy = scan_dataset_releases(registry, storage)
    assert [(item.status, item.release_id) for item in healthy] == [("healthy", result.release_id)]

    shutil.rmtree(result.release_path)
    missing = scan_dataset_releases(registry, storage)
    assert missing[0].status == "missing_artifacts"
    assert missing[0].allowed_actions == []


def test_scan_registers_a_valid_orphan_without_modifying_files(tmp_path: Path) -> None:
    registry, storage, result = _release(tmp_path)
    checksum_before = (result.release_path / "checksums.sha256").read_bytes()
    with session_scope(registry) as session:
        session.execute(delete(DatasetRelease).where(DatasetRelease.id == result.release_id))

    findings = scan_dataset_releases(registry, storage)
    assert findings[0].status == "orphan_directory"
    assert findings[0].allowed_actions == ["register"]

    release = register_orphan_release(registry, storage, result.release_path.relative_to(storage).as_posix())
    assert release.id == result.release_id
    assert release.status == "published"
    assert (result.release_path / "checksums.sha256").read_bytes() == checksum_before


def test_scan_rejects_orphan_with_modified_content(tmp_path: Path) -> None:
    registry, storage, result = _release(tmp_path)
    with session_scope(registry) as session:
        session.execute(delete(DatasetRelease).where(DatasetRelease.id == result.release_id))
    (result.release_path / "train" / "labels" / "sample.txt").write_text("corrupted\n", encoding="utf-8")

    finding = scan_dataset_releases(registry, storage)[0]
    assert finding.status == "checksum_failed"
    assert finding.allowed_actions == []


def test_scan_rejects_orphan_without_existing_annotation_export(tmp_path: Path) -> None:
    registry, storage, result = _release(tmp_path)
    with session_scope(registry) as session:
        session.execute(delete(DatasetRelease).where(DatasetRelease.id == result.release_id))
        session.execute(delete(AnnotationExport).where(AnnotationExport.id == "annotation-lights-native-1"))

    finding = scan_dataset_releases(registry, storage)[0]
    assert finding.status == "missing_provenance"
    assert finding.allowed_actions == []
