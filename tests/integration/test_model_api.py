import json
from pathlib import Path

from fastapi.testclient import TestClient

from yolo_factory.api.app import create_app
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, ModelVersionRecord, Task
from yolo_factory.training.models import TrainingRunSpec
from yolo_factory.training.repository import TrainingRunRepository


class PassingGates:
    def run(self, model_id: str, payload: dict):
        report = Path(payload["pt_path"]).parent / "consistency-report.json"
        report.write_text("{}", encoding="utf-8")
        return ({
            "passed": True,
            "gates": {"training": True, "pt": True, "onnx": True, "consistency": True},
            "artifacts": {"pt": {"path": payload["pt_path"], "sha256": "a" * 64, "size_bytes": 4}, "onnx": {"path": "best.onnx", "sha256": "b" * 64, "size_bytes": 8}},
            "environment": {"ultralytics": "test"},
        }, report)


def _storage(tmp_path: Path) -> Path:
    storage = tmp_path / "storage"
    release = storage / "dataset-releases" / "lights" / "dataset-v1.0.0"
    release.mkdir(parents=True)
    (release / "data.yaml").write_text("path: .\nnames: [light]\n", encoding="utf-8")
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json='["light"]'))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="annotations", task_id="lights", provider_project="lights", provider_version="1", zip_path="annotations.zip", sha256="a" * 64))
    with session_scope(registry) as session:
        session.add(DatasetRelease(id="dataset-lights-1.0.0", task_id="lights", annotation_export_id="annotations", version="1.0.0", release_path=release.relative_to(storage).as_posix(), status="published"))
    training = TrainingRunRepository(registry)
    training.create(TrainingRunSpec("baseline", "detect", "dataset-lights-1.0.0", "yolo11n.pt", 1, 1, 320, "cpu", ("light",), {}), run_id="training-001")
    run_directory = storage / "training-runs" / "training-001"
    training.transition("training-001", "running", run_directory=str(run_directory))
    training.transition("training-001", "evaluating")
    training.transition("training-001", "exporting")
    training.transition("training-001", "verifying")
    best = run_directory / "weights" / "best.pt"
    best.parent.mkdir(parents=True)
    best.write_bytes(b"best")
    (best.parents[1] / "test-metrics.json").write_text(json.dumps({"split": "test", "overall": {"map50_95_box": 0.6}}), encoding="utf-8")
    (best.parents[1] / "quality-report.json").write_text(json.dumps({"verdict": "ready", "confidence": "high"}), encoding="utf-8")
    training.transition("training-001", "completed", artifacts={"best_pt": str(best)}, metrics={"map50": 0.8})
    return storage


def test_registers_gates_publishes_and_archives_model(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        created = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"})
        assert created.status_code == 201
        model_id = created.json()["id"]
        assert created.json()["status"] == "candidate"
        assert created.json()["gates"]["independent_test_available"] is True
        assert created.json()["gates"]["quality_recommended"] is True

        gated = client.post(f"/api/model-versions/{model_id}/gates")
        assert gated.status_code == 200
        assert gated.json()["gates"]["consistency"] is True

        published = client.post(f"/api/model-versions/{model_id}/publish")
        assert published.json()["status"] == "published"
        assert client.get("/api/model-versions").json()[0]["id"] == model_id

        archived = client.post(f"/api/model-versions/{model_id}/archive")
        assert archived.json()["status"] == "archived"


def test_reads_persisted_model_gate_report(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post(
            "/api/model-versions",
            json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"},
        ).json()["id"]
        client.post(f"/api/model-versions/{model_id}/gates")

        response = client.get(f"/api/model-versions/{model_id}/gate-report")

    assert response.status_code == 200
    assert response.json() == {"available": True, "report": {}, "reason": None}


def test_reports_when_model_gate_report_is_not_available(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post(
            "/api/model-versions",
            json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"},
        ).json()["id"]

        never_run = client.get(f"/api/model-versions/{model_id}/gate-report")
        gated = client.post(f"/api/model-versions/{model_id}/gates").json()
        Path(gated["gate_report_path"]).unlink()
        deleted = client.get(f"/api/model-versions/{model_id}/gate-report")

    assert never_run.status_code == 200
    assert never_run.json() == {"available": False, "report": None, "reason": "not_generated"}
    assert deleted.status_code == 200
    assert deleted.json() == {"available": False, "report": None, "reason": "missing"}


def test_rejects_unsafe_or_invalid_model_gate_reports(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    registry = create_registry(storage / "registry" / "factory.db")
    outside = tmp_path / "private-report.json"
    outside.write_text('{"secret": true}', encoding="utf-8")

    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post(
            "/api/model-versions",
            json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"},
        ).json()["id"]
        client.post(f"/api/model-versions/{model_id}/gates")
        with session_scope(registry) as session:
            session.get(ModelVersionRecord, model_id).gate_report_path = str(outside)

        unsafe = client.get(f"/api/model-versions/{model_id}/gate-report")

        invalid = storage / "model-versions" / model_id / "invalid.json"
        invalid.parent.mkdir(parents=True, exist_ok=True)
        invalid.write_text("[]", encoding="utf-8")
        with session_scope(registry) as session:
            session.get(ModelVersionRecord, model_id).gate_report_path = str(invalid)
        non_object = client.get(f"/api/model-versions/{model_id}/gate-report")

        invalid.write_text("{broken", encoding="utf-8")
        malformed = client.get(f"/api/model-versions/{model_id}/gate-report")

    assert unsafe.status_code == 409
    assert unsafe.json()["detail"] == "model gate report is outside storage root"
    assert str(outside) not in unsafe.text
    assert non_object.status_code == 409
    assert non_object.json()["detail"] == "model gate report is invalid"
    assert malformed.status_code == 409
    assert malformed.json()["detail"] == "model gate report is invalid"


def test_model_gate_report_returns_not_found_for_unknown_model(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.get("/api/model-versions/model-missing/gate-report")

    assert response.status_code == 404
    assert response.json()["detail"] == "model version not found"


def test_blocks_publication_without_independent_test_snapshot(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    run_directory = storage / "training-runs" / "training-001"
    (run_directory / "test-metrics.json").unlink()
    (run_directory / "quality-report.json").unlink()

    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"}).json()
        client.post(f"/api/model-versions/{model['id']}/gates")
        response = client.post(f"/api/model-versions/{model['id']}/publish")

    assert model["gates"]["independent_test_available"] is False
    assert response.status_code == 409
    assert "independent test" in response.json()["detail"].lower()


def test_rejects_model_gates_when_dataset_artifact_is_missing(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post(
            "/api/model-versions",
            json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"},
        ).json()["id"]
        (storage / "dataset-releases" / "lights" / "dataset-v1.0.0" / "data.yaml").unlink()

        response = client.post(f"/api/model-versions/{model_id}/gates")

    assert response.status_code == 409
    assert response.json()["detail"] == "dataset release data.yaml is missing"


def test_rejects_model_gates_when_model_weight_is_missing(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post(
            "/api/model-versions",
            json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"},
        ).json()["id"]
        (storage / "training-runs" / "training-001" / "weights" / "best.pt").unlink()

        response = client.post(f"/api/model-versions/{model_id}/gates")

    assert response.status_code == 409
    assert response.json()["detail"] == "model PT artifact is missing"


def test_rejects_registering_the_same_training_run_twice(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        first = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"})
        duplicate = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.1"})

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert "already" in duplicate.json()["detail"].lower()


def test_deletes_candidate_model_and_requires_published_model_archive(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        candidate = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"}).json()
        deleted = client.delete(f"/api/model-versions/{candidate['id']}")
        assert deleted.status_code == 204

    storage = _storage(tmp_path / "published")
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"}).json()["id"]
        client.post(f"/api/model-versions/{model_id}/gates")
        client.post(f"/api/model-versions/{model_id}/publish")
        rejected = client.delete(f"/api/model-versions/{model_id}")
        client.post(f"/api/model-versions/{model_id}/archive")
        archived = client.delete(f"/api/model-versions/{model_id}")

    assert rejected.status_code == 409
    assert "archive" in rejected.json()["detail"].lower()
    assert archived.status_code == 204
