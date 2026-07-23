import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.integration.test_model_api import PassingGates, _storage
from yolo_factory.api.app import create_app
from yolo_factory.registry.database import create_registry


class PassingInference:
    def run(self, run_id: str, payload: dict):
        directory = Path(payload["sources"][0]).parent / run_id
        directory.mkdir()
        media = directory / "annotated.jpg"
        media.write_bytes(b"image")
        result_path = directory / "result.json"
        result = {
            "run_id": run_id,
            "runtime": payload["runtime"],
            "mode": payload["mode"],
            "items": [{"source": payload["sources"][0], "detections": [], "speed": {"inference": 1.5}}],
            "media": [str(media)],
        }
        result_path.write_text(json.dumps(result), encoding="utf-8")
        return result, directory, result_path


class AsyncInference:
    def __init__(self, storage: Path) -> None:
        self.runs = {}
        from yolo_factory.inference.repository import InferenceRunRepository
        self.repository = InferenceRunRepository(create_registry(storage / "registry" / "factory.db"))

    def start(self, run_id: str, payload: dict):
        self.runs[run_id] = payload
        return self.repository.update(run_id, "running", progress=2, message="Started")

    def refresh(self, run_id: str):
        return self.repository.update(run_id, "completed", progress=100, message="Completed")

    def cancel(self, run_id: str):
        return self.repository.update(run_id, "cancelled", progress=2, message="Cancelled")


def _published_model(client: TestClient) -> str:
    created = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"})
    model_id = created.json()["id"]
    assert client.post(f"/api/model-versions/{model_id}/gates").status_code == 200
    assert client.post(f"/api/model-versions/{model_id}/publish").status_code == 200
    return model_id


def test_runs_inference_with_published_model_and_serves_artifact(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    source = storage / "imports" / "inputs" / "sample.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates(), inference_executor=PassingInference())) as client:
        model_id = _published_model(client)
        response = client.post("/api/inference-runs", json={"model_version_id": model_id, "mode": "image", "runtime": "pt", "sources": [str(source)], "confidence": 0.25})

        assert response.status_code == 201
        payload = response.json()
        assert payload["status"] == "completed"
        assert payload["result"]["runtime"] == "pt"
        assert client.get("/api/inference-runs").json()[0]["id"] == payload["id"]
        artifact = client.get("/api/artifacts", params={"path": payload["result"]["media"][0]})
        assert artifact.status_code == 200
        assert artifact.content == b"image"


def test_rejects_unpublished_model_missing_sources_and_path_traversal(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates(), inference_executor=PassingInference())) as client:
        created = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"})
        model_id = created.json()["id"]
        rejected = client.post("/api/inference-runs", json={"model_version_id": model_id, "mode": "image", "runtime": "pt", "sources": [str(storage / "imports" / "missing.jpg")], "confidence": 0.25})
        assert rejected.status_code == 409
        assert client.get("/api/artifacts", params={"path": str(outside)}).status_code == 403


def test_deletes_completed_inference_and_optionally_its_outputs(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    source = storage / "imports" / "inputs" / "sample.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates(), inference_executor=PassingInference())) as client:
        model_id = _published_model(client)
        created = client.post("/api/inference-runs", json={"model_version_id": model_id, "mode": "image", "runtime": "pt", "sources": [str(source)], "confidence": 0.25}).json()
        output_directory = Path(created["output_directory"])

        response = client.delete(f"/api/inference-runs/{created['id']}", params={"delete_artifacts": True})

        assert response.status_code == 204
        assert client.get(f"/api/inference-runs/{created['id']}").status_code == 404
        assert not output_directory.exists()


def test_rejects_deleting_active_inference_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    from yolo_factory.inference.repository import InferenceRunRepository

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        model_id = client.post("/api/model-versions", json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"}).json()["id"]
        repository = InferenceRunRepository(create_registry(storage / "registry" / "factory.db"))
        repository.create(run_id="inference-active", model_version_id=model_id, mode="image", runtime="pt", sources=["input.jpg"], confidence=0.25)
        response = client.delete("/api/inference-runs/inference-active")

    assert response.status_code == 409
    assert "active" in response.json()["detail"].lower()


def test_async_inference_returns_immediately_and_exposes_refresh_and_cancel(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    source = storage / "imports" / "inputs" / "sample.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    executor = AsyncInference(storage)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates(), inference_executor=executor)) as client:
        model_id = _published_model(client)
        started = client.post("/api/inference-runs", json={"model_version_id": model_id, "mode": "image", "runtime": "pt", "sources": [str(source)], "confidence": 0.25})
        run_id = started.json()["id"]
        refreshed = client.post(f"/api/inference-runs/{run_id}/refresh")
        cancelled = client.post(f"/api/inference-runs/{run_id}/cancel")

    assert started.status_code == 201
    assert started.json()["status"] == "running"
    assert refreshed.json()["status"] == "completed"
    assert cancelled.json()["status"] == "cancelled"


def test_runs_inference_with_unpublished_candidate_model(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    source = storage / "imports" / "inputs" / "sample.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    with TestClient(create_app(storage_root=storage, training_engine="simulation", inference_executor=PassingInference())) as client:
        candidate = client.post(
            "/api/model-versions",
            json={"training_run_id": "training-001", "name": "lights", "version": "1.0.0"},
        ).json()
        response = client.post("/api/inference-runs", json={
            "model_version_id": candidate["id"], "mode": "image", "runtime": "pt",
            "sources": [str(source)], "confidence": 0.25,
        })

    assert response.status_code == 201
    assert response.json()["model_version_id"] == candidate["id"]


def test_imports_reuses_and_protects_external_test_model(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    inspected_arguments = []

    def inspector(path, artifact_format, expected_task):
        inspected_arguments.append((path, artifact_format, expected_task))
        return {"task_type": "segment", "class_names": ["tag"]}

    with TestClient(create_app(
        storage_root=storage, training_engine="simulation", inference_executor=PassingInference(),
        imported_model_inspector=inspector,
    )) as client:
        imported_response = client.post(
            "/api/imported-models",
            data={"name": "external segmenter", "task_type": "segment", "class_names": "[]"},
            files={"file": ("best.pt", b"external-model", "application/octet-stream")},
        )
        assert imported_response.status_code == 201
        imported = imported_response.json()
        artifact = Path(imported["artifact"]["path"])
        assert artifact.is_file()
        assert artifact.is_relative_to(storage / "imported-models")
        assert imported["artifact"]["exists"] is True
        assert imported["artifact"]["sha256"]
        assert imported["class_names"] == ["tag"]
        assert inspected_arguments == [(artifact, "pt", "segment")]
        assert client.get("/api/imported-models").json()[0]["id"] == imported["id"]

        inference = client.post(
            "/api/inference-runs/upload",
            data={
                "imported_model_id": imported["id"], "mode": "image",
                "runtime": "pt", "confidence": "0.25",
            },
            files=[("files", ("sample.jpg", b"image", "image/jpeg"))],
        )
        blocked_delete = client.delete(f"/api/imported-models/{imported['id']}")

    assert inference.status_code == 201
    assert inference.json()["imported_model_id"] == imported["id"]
    assert blocked_delete.status_code == 409


def test_rejects_invalid_imported_model_extension(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.post(
            "/api/imported-models",
            data={"name": "bad", "task_type": "detect", "class_names": "[]"},
            files={"file": ("model.txt", b"bad", "text/plain")},
        )

    assert response.status_code == 422
