import io
import json
import zipfile
from pathlib import Path

import yaml
from fastapi.testclient import TestClient
from PIL import Image

from tests.integration.test_inference_api import PassingInference, _published_model
from tests.integration.test_model_api import PassingGates, _storage as _model_storage
from tests.integration.test_training_api import _request, _storage as _training_storage
from yolo_factory.api.app import create_app
from yolo_factory.config.models import TaskConfig
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import Task


def _annotation_zip() -> bytes:
    stream = io.BytesIO()
    image = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(image, format="JPEG")
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("train/images/sample.jpg", image.getvalue())
        archive.writestr("train/labels/sample.txt", "0 0.5 0.5 0.25 0.25\n")
        archive.writestr(
            "data.yaml",
            yaml.safe_dump({"train": "train/images", "val": "train/images", "nc": 1, "names": ["light"]}),
        )
    return stream.getvalue()


def _annotation_app(tmp_path: Path):
    storage = tmp_path / "storage"
    configs = tmp_path / "tasks"
    configs.mkdir()
    (configs / "lights.yaml").write_text(
        yaml.safe_dump(
            TaskConfig(
                task_id="lights",
                task_type="detect",
                classes=["light"],
                annotation_format="yolo-detect",
            ).model_dump()
        ),
        encoding="utf-8",
    )
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json=json.dumps(["light"])))
    return create_app(storage_root=storage, task_config_dir=configs, training_engine="simulation"), storage


def test_uploads_annotation_zip_without_server_path(tmp_path: Path) -> None:
    app, storage = _annotation_app(tmp_path)
    with TestClient(app) as client:
        response = client.post(
            "/api/annotation-imports/upload",
            data={"task_id": "lights", "project": "lights", "provider_version": "1"},
            files={"file": ("roboflow.zip", _annotation_zip(), "application/zip")},
        )

    assert response.status_code == 201
    assert response.json()["sample_count"] == 1
    upload_root = storage / "imports" / "annotation-uploads"
    assert not upload_root.exists() or not any(upload_root.rglob("*"))


def test_restricts_annotation_server_path_to_imports_directory(tmp_path: Path) -> None:
    app, _ = _annotation_app(tmp_path)
    outside = tmp_path / "outside.zip"
    outside.write_bytes(_annotation_zip())
    with TestClient(app) as client:
        response = client.post(
            "/api/annotation-imports",
            json={"task_id": "lights", "archive_path": str(outside), "project": "lights", "provider_version": "1"},
        )

    assert response.status_code == 403


def test_uploads_inference_media_and_starts_run(tmp_path: Path) -> None:
    storage = _model_storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates(), inference_executor=PassingInference())) as client:
        model_id = _published_model(client)
        response = client.post(
            "/api/inference-runs/upload",
            data={"model_version_id": model_id, "mode": "image", "runtime": "pt", "confidence": "0.25"},
            files=[("files", ("sample.jpg", b"image", "image/jpeg"))],
        )
        uploaded_source = Path(response.json()["sources"][0]) if response.status_code == 201 else None
        if response.status_code == 201:
            deleted = client.delete(f"/api/inference-runs/{response.json()['id']}", params={"delete_artifacts": True})

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "completed"
    assert uploaded_source is not None
    assert deleted.status_code == 204
    assert not uploaded_source.exists()
    assert uploaded_source.is_relative_to(storage)


def test_restricts_inference_server_paths_to_imports_directory(tmp_path: Path) -> None:
    storage = _model_storage(tmp_path)
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"image")
    with TestClient(create_app(storage_root=storage, training_engine="simulation", model_gate_executor=PassingGates(), inference_executor=PassingInference())) as client:
        model_id = _published_model(client)
        response = client.post(
            "/api/inference-runs",
            json={"model_version_id": model_id, "mode": "image", "runtime": "pt", "sources": [str(outside)], "confidence": 0.25},
        )

    assert response.status_code == 403


def test_uploads_custom_training_weight_into_storage(tmp_path: Path) -> None:
    storage = _training_storage(tmp_path)
    payload = _request()
    payload.pop("base_model")
    payload["selected_classes"] = json.dumps([])
    payload["class_aliases"] = json.dumps({})
    payload.update({
        "preset_id": "custom", "patience": 0, "optimizer": "AdamW",
        "close_mosaic": 2, "augment_profile": "standard",
        "augmentation": json.dumps({"mosaic": 0.8, "mixup": 0.1}),
    })
    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.2)) as client:
        response = client.post(
            "/api/training-runs/upload",
            data={key: str(value) for key, value in payload.items()},
            files={"base_model_file": ("custom.pt", b"weights", "application/octet-stream")},
        )
        if response.status_code == 201:
            client.post(f"/api/training-runs/{response.json()['id']}/cancel")
            model_path = Path(response.json()["base_model"])
            deleted = client.delete(f"/api/training-runs/{response.json()['id']}", params={"delete_artifacts": True})

    assert response.status_code == 201
    assert response.json()["patience"] == 0
    assert response.json()["optimizer"] == "AdamW"
    assert response.json()["close_mosaic"] == 2
    assert response.json()["augmentation"]["mosaic"] == 0.8
    assert deleted.status_code == 204
    assert not model_path.exists()
    assert model_path.is_relative_to(storage)


def test_rejects_non_pt_custom_training_weight(tmp_path: Path) -> None:
    storage = _training_storage(tmp_path)
    payload = _request()
    payload.pop("base_model")
    payload["selected_classes"] = json.dumps([])
    payload["class_aliases"] = json.dumps({})
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.post(
            "/api/training-runs/upload",
            data={key: str(value) for key, value in payload.items()},
            files={"base_model_file": ("custom.txt", b"weights", "text/plain")},
        )

    assert response.status_code == 422
    upload_root = storage / "model-weights" / "uploads"
    assert not upload_root.exists() or not any(upload_root.rglob("*"))


def test_rejects_oversized_uploaded_training_weight_and_removes_staging_data(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YOLO_FACTORY_MAX_UPLOAD_BYTES", "4")
    storage = _training_storage(tmp_path)
    payload = _request()
    payload.pop("base_model")
    payload["selected_classes"] = json.dumps([])
    payload["class_aliases"] = json.dumps({})

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.post(
            "/api/training-runs/upload",
            data={key: str(value) for key, value in payload.items()},
            files={"base_model_file": ("custom.pt", b"12345", "application/octet-stream")},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "upload exceeds configured 4 byte limit"
    upload_root = storage / "model-weights" / "uploads"
    assert not upload_root.exists() or not any(upload_root.rglob("*"))
