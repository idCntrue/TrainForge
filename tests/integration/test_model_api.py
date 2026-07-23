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
        attempt = Path(payload["pt_path"]).parents[3] / "model-versions" / model_id / "gate-runs" / "test-attempt"
        attempt.mkdir(parents=True, exist_ok=True)
        report = attempt / "result.json"
        report.write_text("{}", encoding="utf-8")
        onnx = attempt / "exported" / "source.onnx"
        onnx.parent.mkdir()
        onnx.write_bytes(b"onnx")
        return ({
            "passed": True,
            "gates": {"training": True, "pt": True, "onnx": True, "consistency": True, "mask_consistency": False},
            "artifacts": {"pt": {"path": payload["pt_path"], "sha256": "a" * 64, "size_bytes": 4}, "onnx": {"path": str(onnx), "sha256": "b" * 64, "size_bytes": 4}},
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
        assert created.json()["artifacts"]["pt"]["exists"] is True
        assert Path(created.json()["artifacts"]["pt"]["path"]).is_absolute()
        assert created.json()["gates"]["independent_test_available"] is True
        assert created.json()["gates"]["quality_recommended"] is True

        gated = client.post(f"/api/model-versions/{model_id}/gates")
        assert gated.status_code == 200
        assert gated.json()["gates"]["consistency"] is True
        assert gated.json()["gates"]["mask_consistency"] is False
        assert gated.json()["status"] == "candidate"
        assert "gate-runs" in gated.json()["artifacts"]["onnx"]["path"]

        published = client.post(f"/api/model-versions/{model_id}/publish")
        assert published.json()["status"] == "published"
        assert client.get("/api/model-versions").json()[0]["id"] == model_id

        archived = client.post(f"/api/model-versions/{model_id}/archive")
        assert archived.json()["status"] == "archived"


def test_exports_published_model_release_bundle(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"}).json()["id"]
        client.post(f"/api/model-versions/{model_id}/gates")
        client.post(f"/api/model-versions/{model_id}/publish")
        response = client.get(f"/api/model-versions/{model_id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "lights-v1.0.0.zip" in response.headers["content-disposition"]
    import io, zipfile
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.read("classes.txt") == b"light\n"
        assert b"D:\\" not in archive.read("manifest.json")


def _write_gate_attempt(storage: Path, model_id: str, run_id: str, *, passed: bool = True) -> Path:
    attempt = storage / "model-versions" / model_id / "gate-runs" / run_id
    exported = attempt / "exported" / "source.onnx"
    exported.parent.mkdir(parents=True)
    exported.write_bytes(run_id.encode())
    report = attempt / "result.json"
    report.write_text(json.dumps({
        "passed": passed,
        "gates": {
            "training": True, "pt": True, "onnx": True,
            "consistency": passed, "mask_consistency": passed,
        },
        "artifacts": {
            "pt": {"path": "best.pt", "sha256": "a" * 64, "size_bytes": 4},
            "onnx": {"path": str(exported), "sha256": "b" * 64, "size_bytes": exported.stat().st_size},
        },
        "environment": {"ultralytics": "test"},
        "samples": [],
    }), encoding="utf-8")
    return attempt


def test_lists_and_deletes_historical_gate_run_with_files(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"}).json()["id"]
        current = client.post(f"/api/model-versions/{model_id}/gates").json()
        historical = _write_gate_attempt(storage, model_id, "historical-run")

        listed = client.get(f"/api/model-versions/{model_id}/gate-runs")
        deleted = client.delete(f"/api/model-versions/{model_id}/gate-runs/historical-run")

    assert listed.status_code == 200
    assert {run["id"] for run in listed.json()} == {"test-attempt", "historical-run"}
    assert deleted.status_code == 200
    assert deleted.json()["fallback_run_id"] is None
    assert deleted.json()["deleted_size_bytes"] > 0
    assert not historical.exists()
    assert deleted.json()["model"]["gate_report_path"] == current["gate_report_path"]


def test_deleting_active_gate_run_falls_back_to_previous_completed_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"}).json()["id"]
        older = _write_gate_attempt(storage, model_id, "older-run")
        gated = client.post(f"/api/model-versions/{model_id}/gates").json()
        active_run_id = Path(gated["gate_report_path"]).parent.name

        response = client.delete(f"/api/model-versions/{model_id}/gate-runs/{active_run_id}")

    assert response.status_code == 200
    assert response.json()["fallback_run_id"] == "older-run"
    assert response.json()["model"]["gate_report_path"] == str(older / "result.json")
    assert response.json()["model"]["artifacts"]["onnx"]["path"] == str(older / "exported" / "source.onnx")


def test_deleting_last_active_gate_run_resets_model_without_training_artifact_loss(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    training_pt = storage / "training-runs" / "training-001" / "weights" / "best.pt"
    training_onnx = training_pt.with_suffix(".onnx")
    training_onnx.write_bytes(b"training-onnx")
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"}).json()["id"]
        gated = client.post(f"/api/model-versions/{model_id}/gates").json()
        active_run_id = Path(gated["gate_report_path"]).parent.name

        response = client.delete(f"/api/model-versions/{model_id}/gate-runs/{active_run_id}")

    assert response.status_code == 200
    assert response.json()["fallback_run_id"] is None
    assert response.json()["model"]["status"] == "blocked"
    assert response.json()["model"]["gates"]["onnx"] is False
    assert response.json()["model"]["gate_report_path"] is None
    assert training_pt.read_bytes() == b"best"
    assert training_onnx.read_bytes() == b"training-onnx"


def test_rejects_deleting_active_gate_of_published_model_and_invalid_run_id(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates())) as client:
        model_id = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"}).json()["id"]
        gated = client.post(f"/api/model-versions/{model_id}/gates").json()
        active_run_id = Path(gated["gate_report_path"]).parent.name
        client.post(f"/api/model-versions/{model_id}/publish")

        protected = client.delete(f"/api/model-versions/{model_id}/gate-runs/{active_run_id}")
        invalid = client.delete(f"/api/model-versions/{model_id}/gate-runs/invalid!run")

    assert protected.status_code == 409
    assert "published" in protected.json()["detail"].lower()
    assert invalid.status_code == 422


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


def test_allows_multiple_versions_from_one_training_run_but_rejects_duplicate_identity(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        first = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"})
        second = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.1"})
        duplicate = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.1"})

    assert first.status_code == 201
    assert second.status_code == 201
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
