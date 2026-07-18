import json
from pathlib import Path

import pytest
import yaml
from PIL import Image

from yolo_factory.config.models import TaskConfig
from yolo_factory.datasets.release import release_dataset
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task


class RecordingDvc:
    def __init__(self) -> None:
        self.paths: list[Path] = []

    def add(self, path: Path) -> None:
        assert path.exists()
        assert not path.name.endswith(".staging")
        self.paths.append(path)


def _arrange(tmp_path: Path) -> tuple[TaskConfig, object, Path]:
    storage = tmp_path / "storage"
    extracted = storage / "annotation-exports" / "lights" / "rf" / "1" / "extracted"
    colors = {"train": (255, 0, 0), "val": (0, 255, 0), "test": (0, 0, 255)}
    for split in ("train", "val", "test"):
        image = extracted / split / "images" / f"{split}.jpg"
        label = extracted / split / "labels" / f"{split}.txt"
        image.parent.mkdir(parents=True)
        label.parent.mkdir(parents=True)
        Image.new("RGB", (16, 16), colors[split]).save(image)
        label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    task = TaskConfig(
        task_id="lights",
        task_type="detect",
        classes=["red"],
        annotation_format="yolo-detect",
    )
    registry = create_registry(tmp_path / "registry.db")
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json=json.dumps(["red"])))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="annotation-lights-rf-1", task_id="lights", provider_project="rf", provider_version="1", zip_path="annotation-exports/lights/rf/1/original.zip", sha256="a" * 64))
    return task, registry, storage


def test_releases_standard_immutable_dataset(tmp_path: Path) -> None:
    task, registry, storage = _arrange(tmp_path)
    dvc = RecordingDvc()
    result = release_dataset(
        task,
        "annotation-lights-rf-1",
        "1.0.0",
        storage,
        registry,
        dvc,
        display_name="电梯灯数据集",
    )
    assert result.release_path.name == "dataset-v1.0.0"
    assert (result.release_path / "data.yaml").exists()
    assert (result.release_path / "manifest.yaml").exists()
    assert (result.release_path / "checksums.sha256").exists()
    assert (result.release_path / "validation-report.json").exists()
    assert dvc.paths == [result.release_path]
    with session_scope(registry) as session:
        release = session.get(DatasetRelease, result.release_id)
        assert release.status == "published"
        assert release.display_name == "电梯灯数据集"

    with pytest.raises(ValueError, match="already exists"):
        release_dataset(
            task,
            "annotation-lights-rf-1",
            "1.0.0",
            storage,
            registry,
            dvc,
            display_name="电梯灯数据集",
        )


def test_rejects_invalid_semantic_version(tmp_path: Path) -> None:
    task, registry, storage = _arrange(tmp_path)
    with pytest.raises(ValueError, match="semantic version"):
        release_dataset(
            task,
            "annotation-lights-rf-1",
            "latest",
            storage,
            registry,
            RecordingDvc(),
            display_name="电梯灯数据集",
        )


def test_single_split_release_reuses_train_for_smoke_validation(tmp_path: Path) -> None:
    task, registry, storage = _arrange(tmp_path)
    extracted = storage / "annotation-exports" / "lights" / "rf" / "1" / "extracted"
    for split in ("val", "test"):
        import shutil
        shutil.rmtree(extracted / split)

    result = release_dataset(
        task,
        "annotation-lights-rf-1",
        "0.1.0",
        storage,
        registry,
        RecordingDvc(),
        display_name="电梯灯数据集",
    )
    data = yaml.safe_load((result.release_path / "data.yaml").read_text(encoding="utf-8"))

    assert data["train"] == "train/images"
    assert data["val"] == "train/images"
    assert data["test"] == "train/images"


def test_releases_native_source_index_with_requested_split_ratios(tmp_path: Path) -> None:
    task, registry, storage = _arrange(tmp_path)
    extracted = storage / "annotation-exports" / "lights" / "rf" / "1" / "extracted"
    import shutil
    shutil.rmtree(extracted)
    entries = []
    for index in range(10):
        image = extracted / "train" / "images" / f"sample-{index}.jpg"
        label = extracted / "train" / "labels" / f"sample-{index}.txt"
        image.parent.mkdir(parents=True, exist_ok=True)
        label.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 16), (index * 20, 0, 0)).save(image)
        label.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
        entries.append({"frame_id": f"frame-{index}", "image_name": image.name, "source_group": f"video-{index}"})
    (extracted / "source-index.json").write_text(json.dumps(entries), encoding="utf-8")

    result = release_dataset(
        task, "annotation-lights-rf-1", "2.0.0", storage, registry, RecordingDvc(),
        display_name="电梯灯数据集",
        split_ratios={"train": 70, "val": 20, "test": 10}, split_seed=42,
    )
    manifest = __import__("yaml").safe_load((result.release_path / "manifest.yaml").read_text(encoding="utf-8"))

    assert manifest["split_counts"] == {"train": 7, "val": 2, "test": 1}
    assert manifest["requested_ratios"] == {"train": 70, "val": 20, "test": 10}
    assert sum(len(list((result.release_path / split / "images").glob("*"))) for split in ("train", "val", "test")) == 10
