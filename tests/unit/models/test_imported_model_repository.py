from pathlib import Path

import pytest

from yolo_factory.models.imported_repository import (
    ImportedModelRepository,
    ReferencedImportedModelDeletion,
)
from yolo_factory.registry.database import create_registry
from yolo_factory.inference.repository import InferenceRunRepository


def test_creates_lists_and_deletes_unreferenced_imported_model(tmp_path: Path) -> None:
    repository = ImportedModelRepository(create_registry(tmp_path / "factory.db"))

    created = repository.create(
        model_id="import-1",
        name="external segmenter",
        task_type="segment",
        artifact_format="pt",
        original_name="best.pt",
        artifact_path=str(tmp_path / "best.pt"),
        size_bytes=123,
        sha256="a" * 64,
        class_names=("tag",),
    )

    assert created.id == "import-1"
    assert repository.list()[0].artifact_format == "pt"
    assert repository.delete("import-1").id == "import-1"


def test_rejects_deleting_imported_model_referenced_by_inference(tmp_path: Path) -> None:
    registry = create_registry(tmp_path / "factory.db")
    repository = ImportedModelRepository(registry)
    repository.create(
        model_id="import-1", name="external", task_type="detect", artifact_format="onnx",
        original_name="model.onnx", artifact_path=str(tmp_path / "model.onnx"),
        size_bytes=20, sha256="b" * 64, class_names=(),
    )
    InferenceRunRepository(registry).create(
        run_id="run-1", model_version_id=None, imported_model_id="import-1",
        mode="image", runtime="onnx", sources=["input.jpg"], confidence=0.25,
    )

    with pytest.raises(ReferencedImportedModelDeletion, match="run-1"):
        repository.delete("import-1")
