from pathlib import Path

import pytest

from yolo_factory.models.domain import ModelVersionSpec
from yolo_factory.models.repository import InvalidModelTransition, ModelVersionRepository
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task
from yolo_factory.training.models import TrainingRunSpec
from yolo_factory.training.repository import TrainingRunRepository


def _repository(path: Path) -> ModelVersionRepository:
    registry = create_registry(path)
    with session_scope(registry) as session:
        if session.get(Task, "lights") is None:
            session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json='["light"]'))
    with session_scope(registry) as session:
        if session.get(AnnotationExport, "annotations") is None:
            session.add(AnnotationExport(id="annotations", task_id="lights", provider_project="lights", provider_version="1", zip_path="annotations.zip", sha256="a" * 64))
    with session_scope(registry) as session:
        if session.get(DatasetRelease, "dataset-lights-1.0.0") is None:
            session.add(DatasetRelease(id="dataset-lights-1.0.0", task_id="lights", annotation_export_id="annotations", version="1.0.0", release_path="dataset", status="published"))
    training = TrainingRunRepository(registry)
    if training.get("training-001") is None:
        training.create(TrainingRunSpec("baseline", "detect", "dataset-lights-1.0.0", "yolo11n.pt", 1, 1, 320, "cpu", ("light",), {}), run_id="training-001")
        training.transition("training-001", "running")
        training.transition("training-001", "evaluating")
        training.transition("training-001", "exporting")
        training.transition("training-001", "verifying")
        training.transition("training-001", "completed", artifacts={"best_pt": "runs/best.pt"}, metrics={"map50": 0.8})
    return ModelVersionRepository(registry)


def _spec() -> ModelVersionSpec:
    return ModelVersionSpec(
        name="lights-detect",
        version="1.0.0",
        task_type="detect",
        training_run_id="training-001",
        dataset_release_id="dataset-lights-1.0.0",
        selected_classes=("light",),
        class_aliases={},
        pt_path="runs/best.pt",
        metrics={"map50": 0.8},
        quality_report={"verdict": "ready", "confidence": "high"},
    )


def test_candidate_survives_registry_reopen(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    created = _repository(database).create(_spec(), model_id="model-001")

    loaded = _repository(database).get_required("model-001")

    assert loaded == created
    assert loaded.status == "candidate"


def test_requires_all_release_gates_before_publish(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), model_id="model-001")
    repository.update_gates("model-001", {"training": True, "pt": True, "onnx": False, "consistency": False})

    with pytest.raises(InvalidModelTransition):
        repository.publish("model-001")

    repository.update_gates("model-001", {"training": True, "pt": True, "onnx": True, "consistency": True})
    published = repository.publish("model-001")
    archived = repository.archive("model-001")

    assert published.status == "published"
    assert archived.status == "archived"
