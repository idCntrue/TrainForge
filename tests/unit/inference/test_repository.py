from pathlib import Path

from yolo_factory.inference.repository import InferenceRunRepository
from yolo_factory.models.domain import ModelVersionSpec
from yolo_factory.models.repository import ModelVersionRepository
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task, TrainingRunRecord


def _repository(path: Path) -> InferenceRunRepository:
    registry = create_registry(path)
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json='["light"]'))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="annotations", task_id="lights", provider_project="lights", provider_version="1", zip_path="annotations.zip", sha256="a" * 64))
    with session_scope(registry) as session:
        session.add(DatasetRelease(id="dataset-lights-1.0.0", task_id="lights", annotation_export_id="annotations", version="1.0.0", release_path="datasets/lights/1.0.0", status="published"))
    with session_scope(registry) as session:
        session.add(TrainingRunRecord(id="training-001", name="baseline", task_type="detect", dataset_release_id="dataset-lights-1.0.0", base_model="yolo11n.pt", config_json="{}", status="completed", progress=100, phase="completed", message="Completed"))
    models = ModelVersionRepository(registry)
    models.create(ModelVersionSpec(
        "lights", "1.0.0", "detect", "training-001", "dataset-lights-1.0.0",
        ("light",), {}, "best.pt", {},
        quality_report={"verdict": "ready", "confidence": "high"},
    ), model_id="model-001")
    models.update_gates("model-001", {"training": True, "pt": True, "onnx": True, "consistency": True})
    models.publish("model-001")
    return InferenceRunRepository(registry)


def test_inference_run_survives_reopen_and_persists_result(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    repository = _repository(database)
    created = repository.create(run_id="inference-001", model_version_id="model-001", mode="image", runtime="pt", sources=["input.jpg"], confidence=0.25)

    repository.update("inference-001", "running", progress=10, message="Running", pid=4321, run_directory="runs/inference-001")
    completed = repository.update("inference-001", "completed", progress=100, message="Completed", output_directory="outputs", result_path="result.json")
    reopened = InferenceRunRepository(create_registry(database)).get_required("inference-001")

    assert created["status"] == "queued"
    assert completed["finished_at"] is not None
    assert reopened["status"] == "completed"
    assert reopened["result_path"] == "result.json"
    assert reopened["pid"] == 4321
    assert reopened["run_directory"] == "runs/inference-001"
    assert [run["id"] for run in InferenceRunRepository(create_registry(database)).list()] == ["inference-001"]
