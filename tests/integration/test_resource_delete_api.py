import json
from pathlib import Path

from fastapi.testclient import TestClient

from yolo_factory.api.app import create_app
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, FrameAsset, FrameBatch, InferenceRunRecord, ModelVersionRecord, Task, TrainingRunRecord, VideoAsset, VideoCollection


def _storage(tmp_path: Path) -> Path:
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json='["light"]'))
    with session_scope(registry) as session:
        session.add(VideoCollection(id="collection-1", task_id="lights"))
        session.add(AnnotationExport(id="export-1", task_id="lights", provider_project="native", provider_version="1", zip_path="annotations.zip", sha256="c" * 64))
    with session_scope(registry) as session:
        session.add(VideoAsset(id="video-1", collection_id="collection-1", original_name="input.mp4", stored_path="videos/input.mp4", sha256="a" * 64, size_bytes=10))
        session.add(FrameBatch(id="batch-1", collection_id="collection-1", manifest_path="frame-batches/lights/batch-1/manifest.json"))
        session.add(DatasetRelease(id="release-free", task_id="lights", annotation_export_id="export-1", version="1.0.0", release_path="dataset-releases/lights/free", status="published"))
        session.add(DatasetRelease(id="release-used", task_id="lights", annotation_export_id="export-1", version="2.0.0", release_path="dataset-releases/lights/used", status="published"))
    with session_scope(registry) as session:
        session.add(FrameAsset(id="frame-1", batch_id="batch-1", video_id="video-1", stored_path="frame-batches/lights/batch-1/candidates/frame.jpg", sha256="b" * 64, timestamp_ms=0, frame_index=0, status="candidate"))
    with session_scope(registry) as session:
        session.add(TrainingRunRecord(id="training-1", name="used", task_type="detect", dataset_release_id="release-used", base_model="yolo11n.pt", config_json=json.dumps({"epochs": 1, "batch": 1, "image_size": 320, "device": "cpu"}), status="cancelled", progress=0, phase="cancelled", message="Cancelled"))
    (storage / "frame-batches" / "lights" / "batch-1").mkdir(parents=True)
    return storage


def test_deletes_batch_before_collection_and_rejects_dataset_in_use(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        blocked_collection = client.delete("/api/video-collections/collection-1")
        deleted_batch = client.delete("/api/frame-batches/batch-1", params={"delete_artifacts": True})
        deleted_collection = client.delete("/api/video-collections/collection-1")
        deleted_release = client.delete("/api/dataset-releases/release-free")
        blocked_release = client.delete("/api/dataset-releases/release-used")

    assert blocked_collection.status_code == 409
    assert deleted_batch.status_code == 204
    assert not (storage / "frame-batches" / "lights" / "batch-1").exists()
    assert deleted_collection.status_code == 204
    assert deleted_release.status_code == 204
    assert blocked_release.status_code == 409
    assert "training" in blocked_release.json()["detail"].lower()


def test_batch_duplicate_query_works_for_registered_collection(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.get("/api/frame-batches/batch-1/duplicates")

    assert response.status_code == 200


def test_cascade_deletes_video_collection_with_its_batches(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.delete(
            "/api/video-collections/collection-1",
            params={"cascade": True, "delete_artifacts": True},
        )

        assert response.status_code == 204
        assert client.get("/api/video-collections").json() == []
        assert client.get("/api/frame-batches").json() == []
        annotation_page = client.get("/api/annotation-images").json()
        assert annotation_page["items"] == []
        assert annotation_page["total"] == 0
        assert not (storage / "frame-batches" / "lights" / "batch-1").exists()


def test_cascade_deletes_dataset_and_all_downstream_records(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(ModelVersionRecord(
            id="model-1",
            name="lights",
            version="1.0.0",
            task_type="detect",
            training_run_id="training-1",
            dataset_release_id="release-used",
            config_json=json.dumps({"selected_classes": ["light"], "class_aliases": {}, "pt_path": "best.pt", "metrics": {}, "artifacts": {}, "environment": {}}),
            status="published",
            gates_json=json.dumps({"training": True, "pt": True, "onnx": True, "consistency": True}),
        ))
    with session_scope(registry) as session:
        session.add(InferenceRunRecord(
            id="inference-1",
            model_version_id="model-1",
            mode="image",
            runtime="pt",
            config_json=json.dumps({"sources": ["input.jpg"], "confidence": 0.25}),
            status="completed",
            progress=100,
            message="Completed",
        ))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.delete("/api/dataset-releases/release-used", params={"cascade": True})

        assert response.status_code == 204
        assert client.get("/api/training-runs").json() == []
        assert client.get("/api/model-versions").json() == []
        assert client.get("/api/inference-runs").json() == []
        assert [item["id"] for item in client.get("/api/dataset-releases").json()] == ["release-free"]


def test_dataset_cascade_deletes_managed_uploaded_base_weight(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    upload_directory = storage / "model-weights" / "uploads" / "upload-dataset"
    upload_directory.mkdir(parents=True)
    uploaded_weight = upload_directory / "custom.pt"
    uploaded_weight.write_bytes(b"weights")
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.get(TrainingRunRecord, "training-1").base_model = str(uploaded_weight)

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.delete(
            "/api/dataset-releases/release-used",
            params={"cascade": True, "delete_artifacts": True},
        )

    assert response.status_code == 204
    assert not upload_directory.exists()


def test_rejects_unsafe_cascade_artifacts_without_deleting_records(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.get(VideoAsset, "video-1").stored_path = str(outside)

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.delete(
            "/api/video-collections/collection-1",
            params={"cascade": True, "delete_artifacts": True},
        )

        assert response.status_code == 409
        assert [item["id"] for item in client.get("/api/video-collections").json()] == ["collection-1"]
        assert [item["id"] for item in client.get("/api/frame-batches").json()] == ["batch-1"]
        assert outside.exists()


def test_rejects_unsafe_training_cascade_before_database_changes(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    outside = tmp_path / "outside.pt"
    outside.write_bytes(b"outside")
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(ModelVersionRecord(
            id="model-outside",
            name="lights",
            version="1.0.0",
            task_type="detect",
            training_run_id="training-1",
            dataset_release_id="release-used",
            config_json=json.dumps({"selected_classes": ["light"], "class_aliases": {}, "pt_path": str(outside), "metrics": {}, "artifacts": {}, "environment": {}}),
            status="candidate",
            gates_json="{}",
        ))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.delete(
            "/api/training-runs/training-1",
            params={"cascade": True, "delete_artifacts": True},
        )

        assert response.status_code == 409
        assert [item["id"] for item in client.get("/api/training-runs").json()] == ["training-1"]
        assert [item["id"] for item in client.get("/api/model-versions").json()] == ["model-outside"]
        assert outside.exists()


def test_training_delete_preserves_uploaded_weight_referenced_by_another_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    upload_directory = storage / "model-weights" / "uploads" / "shared-upload"
    upload_directory.mkdir(parents=True)
    uploaded_weight = upload_directory / "custom.pt"
    uploaded_weight.write_bytes(b"weights")
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.get(TrainingRunRecord, "training-1").base_model = str(uploaded_weight)
        session.add(TrainingRunRecord(
            id="training-2",
            name="shared",
            task_type="detect",
            dataset_release_id="release-free",
            base_model=str(uploaded_weight),
            config_json=json.dumps({"epochs": 1, "batch": 1, "image_size": 320, "device": "cpu"}),
            status="cancelled",
            progress=0,
            phase="cancelled",
            message="Cancelled",
        ))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.delete(
            "/api/training-runs/training-1",
            params={"delete_artifacts": True},
        )

    assert response.status_code == 204
    assert upload_directory.exists()
    assert uploaded_weight.is_file()


def test_deletes_unused_task(tmp_path: Path) -> None:
    config_dir = tmp_path / "task-configs"
    with TestClient(create_app(storage_root=tmp_path / "storage", task_config_dir=config_dir, training_engine="simulation")) as client:
        assert client.post("/api/tasks", json={
            "id": "unused-task",
            "task_type": "detect",
            "classes": ["object"],
        }).status_code == 201

        response = client.delete("/api/tasks/unused-task")

        assert response.status_code == 204
        assert client.get("/api/tasks").json() == []
        assert not (config_dir / "unused-task.yaml").exists()
        recreated = client.post("/api/tasks", json={
            "id": "unused-task",
            "task_type": "detect",
            "classes": ["object"],
        })
        assert recreated.status_code == 201, recreated.text


def test_rejects_deleting_task_with_dependencies_without_cascade(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, task_config_dir=tmp_path / "task-configs", training_engine="simulation")) as client:
        response = client.delete("/api/tasks/lights")

        assert response.status_code == 409
        assert "referenced" in response.json()["detail"].lower()
        assert [item["id"] for item in client.get("/api/tasks").json()] == ["lights"]


def test_cascade_deletes_task_and_complete_downstream_chain(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, task_config_dir=tmp_path / "task-configs", training_engine="simulation")) as client:
        response = client.delete("/api/tasks/lights", params={"cascade": True})

        assert response.status_code == 204
        assert client.get("/api/tasks").json() == []
        assert client.get("/api/video-collections").json() == []
        assert client.get("/api/frame-batches").json() == []
        annotation_page = client.get("/api/annotation-images").json()
        assert annotation_page["items"] == []
        assert annotation_page["total"] == 0
        assert client.get("/api/dataset-releases").json() == []
        assert client.get("/api/training-runs").json() == []


def test_task_cascade_deletes_managed_uploaded_base_weight(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    upload_directory = storage / "model-weights" / "uploads" / "upload-task"
    upload_directory.mkdir(parents=True)
    uploaded_weight = upload_directory / "custom.pt"
    uploaded_weight.write_bytes(b"weights")
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.get(TrainingRunRecord, "training-1").base_model = str(uploaded_weight)

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.delete(
            "/api/tasks/lights",
            params={"cascade": True, "delete_artifacts": True},
        )

    assert response.status_code == 204
    assert not upload_directory.exists()
