from dataclasses import replace
from pathlib import Path

import pytest

from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task
from yolo_factory.training.models import TrainingRunSpec
from yolo_factory.training.repository import (
    InvalidTrainingTransition,
    TrainingRunRepository,
)


def _repository(path: Path) -> TrainingRunRepository:
    registry = create_registry(path)
    with session_scope(registry) as session:
        if session.get(Task, "lights") is None:
            session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json='["light"]'))
    with session_scope(registry) as session:
        if session.get(AnnotationExport, "annotation-lights-rf-1") is None:
            session.add(AnnotationExport(id="annotation-lights-rf-1", task_id="lights", provider_project="lights", provider_version="1", zip_path="annotations.zip", sha256="a" * 64))
    with session_scope(registry) as session:
        if session.get(DatasetRelease, "dataset-lights-1.0.0") is None:
            session.add(DatasetRelease(id="dataset-lights-1.0.0", task_id="lights", annotation_export_id="annotation-lights-rf-1", version="1.0.0", release_path="datasets/lights/1.0.0", status="published"))
    return TrainingRunRepository(registry)


def _spec() -> TrainingRunSpec:
    return TrainingRunSpec(
        name="door detect baseline",
        task_type="detect",
        dataset_release_id="dataset-lights-1.0.0",
        base_model="yolo11n.pt",
        epochs=20,
        batch=8,
        image_size=640,
        device="cuda:0",
    )


def test_training_run_survives_registry_reopen(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    created = _repository(database).create(_spec(), run_id="run-001")

    loaded = _repository(database).get("run-001")

    assert loaded == created
    assert loaded.status == "queued"
    assert loaded.progress == 0.0


def test_lists_runs_by_status_newest_first(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-001")
    repository.create(_spec(), run_id="run-002")
    repository.transition("run-002", "running", progress=12.5, phase="training")

    assert [run.id for run in repository.list(status="running")] == ["run-002"]


def test_advances_through_release_gate_states(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-001")

    for status in ("running", "evaluating", "exporting", "verifying", "completed"):
        current = repository.transition("run-001", status)

    assert current.status == "completed"
    assert current.progress == 100.0


def test_rejects_invalid_or_terminal_transition(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-001")

    with pytest.raises(InvalidTrainingTransition):
        repository.transition("run-001", "completed")

    repository.transition("run-001", "cancelled")
    with pytest.raises(InvalidTrainingTransition):
        repository.transition("run-001", "running")


def test_persists_normalized_epoch_metrics_and_artifacts(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-001")
    repository.transition("run-001", "running")

    updated = repository.update_runtime(
        "run-001",
        epoch=3,
        total_epochs=20,
        metrics={"map50": 0.91, "precision": 0.82},
        artifacts={"best_pt": "runs/run-001/best.pt"},
    )

    assert updated.epoch == 3
    assert updated.total_epochs == 20
    assert updated.metrics == {"map50": 0.91, "precision": 0.82}
    assert updated.artifacts == {"best_pt": "runs/run-001/best.pt"}


def test_persists_recovery_lineage_without_schema_migration(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    spec = replace(
        _spec(),
        source_run_id="run-source",
        execution_mode="train",
        retry_strategy="safe",
        request_id="request-123",
        preset_id="cpu-balanced",
        patience=25,
        optimizer="auto",
        close_mosaic=10,
        augment_profile="conservative",
    )

    repository.create(spec, run_id="run-child")
    loaded = repository.get_required("run-child")

    assert loaded.spec.source_run_id == "run-source"
    assert loaded.spec.execution_mode == "train"
    assert loaded.spec.retry_strategy == "safe"
    assert loaded.spec.request_id == "request-123"
    assert repository.find_retry("run-source", "request-123").id == "run-child"
    assert loaded.spec.preset_id == "cpu-balanced"
    assert loaded.spec.patience == 25
    assert loaded.spec.augment_profile == "conservative"
