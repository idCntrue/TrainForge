import json
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from yolo_factory.api.app import create_app
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task
from yolo_factory.training.models import TrainingRunSpec
from yolo_factory.training.repository import TrainingRunRepository
from yolo_factory.training.resource_policy import TrainingResourcePolicy
from yolo_factory.training.ultralytics_adapter import prepare_dataset_view


def _storage(tmp_path: Path) -> Path:
    storage = tmp_path / "storage"
    registry = create_registry(storage / "registry" / "factory.db")
    release_path = storage / "dataset-releases" / "lights" / "dataset-v1.0.0"
    for split in ("train", "val"):
        (release_path / split / "images").mkdir(parents=True)
        (release_path / split / "labels").mkdir(parents=True)
        (release_path / split / "images" / f"{split}.jpg").write_bytes(b"jpg")
        (release_path / split / "labels" / f"{split}.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    (release_path / "data.yaml").write_text(
        "path: .\ntrain: train/images\nval: val/images\nnames: [light]\n",
        encoding="utf-8",
    )
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json=json.dumps(["light"])))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="annotation-lights-rf-1", task_id="lights", provider_project="lights", provider_version="1", zip_path="annotations.zip", sha256="a" * 64))
    with session_scope(registry) as session:
        session.add(DatasetRelease(id="dataset-lights-1.0.0", task_id="lights", annotation_export_id="annotation-lights-rf-1", version="1.0.0", release_path=release_path.relative_to(storage).as_posix(), status="published"))
    return storage


def _request() -> dict:
    return {
        "name": "lights baseline",
        "task_type": "detect",
        "dataset_release_id": "dataset-lights-1.0.0",
        "base_model": "yolo11n.pt",
        "epochs": 5,
        "batch": 2,
        "image_size": 640,
        "device": "cuda:0",
    }


def test_training_fixture_matches_production_layout_and_copies_labels(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    source_yaml = storage / "dataset-releases" / "lights" / "dataset-v1.0.0" / "data.yaml"

    derived_yaml = prepare_dataset_view(
        source_yaml,
        tmp_path / "run",
        selected_classes=["light"],
        class_aliases={"light": "indicator"},
    )

    derived_label = derived_yaml.parent / "train" / "labels" / "train.txt"
    assert derived_label.read_text(encoding="utf-8") == "0 0.5 0.5 0.2 0.2\n"


def _add_segment_release(storage: Path) -> None:
    registry = create_registry(storage / "registry" / "factory.db")
    release_path = storage / "dataset-releases" / "masks" / "dataset-v1.0.0"
    for split in ("train", "val"):
        (release_path / split / "images").mkdir(parents=True)
        (release_path / split / "labels").mkdir(parents=True)
        (release_path / split / "images" / f"{split}.jpg").write_bytes(b"jpg")
        (release_path / split / "labels" / f"{split}.txt").write_text("0 0.1 0.1 0.9 0.1 0.9 0.9\n", encoding="utf-8")
    (release_path / "data.yaml").write_text(
        "path: .\ntrain: train/images\nval: val/images\nnames: [mask]\n",
        encoding="utf-8",
    )
    with session_scope(registry) as session:
        session.add(Task(id="masks", task_type="segment", annotation_format="yolo-seg", classes_json=json.dumps(["mask"])))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="annotation-masks-1", task_id="masks", provider_project="masks", provider_version="1", zip_path="masks.zip", sha256="b" * 64))
    with session_scope(registry) as session:
        session.add(DatasetRelease(id="dataset-masks-1.0.0", task_id="masks", annotation_export_id="annotation-masks-1", version="1.0.0", release_path=release_path.relative_to(storage).as_posix(), status="published"))


def _assert_no_training_side_effects(app, storage: Path) -> None:
    assert app.state.training_repository.list() == []
    assert not (storage / "training-runs").exists()


def test_rejects_unsafe_cpu_parameters_before_creating_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    _add_segment_release(storage)
    app = create_app(storage_root=storage, training_engine="simulation")

    with TestClient(app) as client:
        segment_response = client.post("/api/training-runs", json=_request() | {
            "task_type": "segment",
            "dataset_release_id": "dataset-masks-1.0.0",
            "batch": 3,
            "image_size": 320,
            "device": "cpu",
        })
        image_response = client.post("/api/training-runs", json=_request() | {
            "batch": 2,
            "image_size": 672,
            "device": "cpu",
        })

    assert segment_response.status_code == 422
    assert "batch must be at most 1" in segment_response.json()["detail"]
    assert image_response.status_code == 422
    assert "image size must be at most 640" in image_response.json()["detail"]
    _assert_no_training_side_effects(app, storage)


def test_named_preset_ignores_client_resource_overrides(tmp_path: Path) -> None:
    storage = _storage(tmp_path)

    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.2)) as client:
        response = client.post("/api/training-runs", json=_request() | {
            "preset_id": "cpu-balanced",
            "device": "cpu",
            "epochs": 999,
            "batch": 999,
            "image_size": 4096,
            "patience": 299,
            "optimizer": "AdamW",
            "close_mosaic": 999,
        })
        manifest = json.loads((Path(response.json()["run_directory"]) / "manifest.json").read_text(encoding="utf-8"))
        client.post(f"/api/training-runs/{response.json()['id']}/cancel")

    assert response.status_code == 201
    assert (response.json()["epochs"], response.json()["batch"], response.json()["image_size"]) == (150, 2, 640)
    assert response.json()["preset_id"] == "cpu-balanced"
    assert manifest["spec"]["patience"] == 25
    assert manifest["spec"]["optimizer"] == "auto"
    assert manifest["spec"]["close_mosaic"] == 10
    assert manifest["spec"]["augment_profile"] == "conservative"


def test_validates_custom_training_strategy_parameters(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    app = create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.2)

    with TestClient(app) as client:
        invalid_optimizer = client.post("/api/training-runs", json=_request() | {
            "preset_id": "custom",
            "optimizer": "NotAnOptimizer",
        })
        invalid_close_mosaic = client.post("/api/training-runs", json=_request() | {
            "preset_id": "custom",
            "epochs": 5,
            "close_mosaic": 6,
        })
        accepted = client.post("/api/training-runs", json=_request() | {
            "preset_id": "custom",
            "patience": 0,
            "optimizer": "AdamW",
            "close_mosaic": 5,
        })
        manifest = json.loads((Path(accepted.json()["run_directory"]) / "manifest.json").read_text(encoding="utf-8"))
        client.post(f"/api/training-runs/{accepted.json()['id']}/cancel")

    assert invalid_optimizer.status_code == 422
    assert invalid_close_mosaic.status_code == 422
    assert accepted.status_code == 201
    assert manifest["spec"]["patience"] == 0
    assert manifest["spec"]["optimizer"] == "AdamW"
    assert manifest["spec"]["close_mosaic"] == 5


def test_rejects_low_disk_before_creating_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    app = create_app(
        storage_root=storage,
        training_engine="simulation",
        training_resource_policy=TrainingResourcePolicy.from_environment({}),
        training_disk_usage=lambda _: SimpleNamespace(total=100 * 1024**3, used=95 * 1024**3, free=5 * 1024**3),
    )

    with TestClient(app) as client:
        response = client.post("/api/training-runs", json=_request() | {"device": "cpu"})

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "insufficient_training_storage",
        "message": "训练至少需要 8 GiB 可用空间且保持 10% 空闲；当前为 5.00 GiB（5.00%）",
        "free_gib": 5.0,
        "free_percent": 5.0,
        "required_gib": 8,
        "required_percent": 10,
        "failed_checks": ["absolute", "percentage"],
    }
    _assert_no_training_side_effects(app, storage)


def test_rejects_low_windows_memory_before_creating_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    app = create_app(
        storage_root=storage,
        training_engine="ultralytics",
        training_memory_snapshot=lambda: {
            "windows_available_commit_bytes": 2 * 1024**3,
            "windows_available_physical_bytes": 6 * 1024**3,
            "windows_leaspac_process_count": 30,
            "windows_leaspac_private_bytes": 31 * 1024**3,
        },
    )

    with TestClient(app) as client:
        response = client.post("/api/training-runs", json=_request())

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "insufficient_training_memory"
    assert response.json()["detail"]["failed_checks"] == ["commit"]
    assert response.json()["detail"]["leaspac_process_count"] == 30
    _assert_no_training_side_effects(app, storage)


def test_simulation_training_ignores_windows_memory_gate(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    app = create_app(
        storage_root=storage,
        training_engine="simulation",
        training_step_seconds=0.2,
        training_memory_snapshot=lambda: {
            "windows_available_commit_bytes": 2 * 1024**3,
            "windows_available_physical_bytes": 2 * 1024**3,
        },
    )

    with TestClient(app) as client:
        response = client.post("/api/training-runs", json=_request())
        if response.status_code == 201:
            client.post(f"/api/training-runs/{response.json()['id']}/cancel")

    assert response.status_code == 201


def test_training_preflight_cleans_before_measuring_disk(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    calls: list[str] = []

    def cleanup(_root: Path):
        calls.append("cleanup")

    def usage(_root: Path):
        calls.append("measure")
        return SimpleNamespace(total=100 * 1024**3, used=80 * 1024**3, free=20 * 1024**3)

    app = create_app(
        storage_root=storage,
        training_engine="simulation",
        training_step_seconds=0.2,
        training_storage_cleanup=cleanup,
        training_disk_usage=usage,
    )

    with TestClient(app) as client:
        response = client.post("/api/training-runs", json=_request() | {"device": "cpu"})
        if response.status_code == 201:
            client.post(f"/api/training-runs/{response.json()['id']}/cancel")

    assert response.status_code == 201
    assert calls[:2] == ["cleanup", "measure"]


def test_dataset_quality_endpoint_and_structural_preflight_have_no_run_side_effects(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    release_path = storage / "dataset-releases" / "lights" / "dataset-v1.0.0"
    (release_path / "val" / "images" / "val.jpg").unlink()
    app = create_app(storage_root=storage, training_engine="simulation")

    with TestClient(app) as client:
        quality = client.get("/api/dataset-releases/dataset-lights-1.0.0/quality")
        response = client.post("/api/training-runs", json=_request())

    assert quality.status_code == 200
    assert "empty_val_split" in quality.json()["blockers"]
    assert response.status_code == 409
    assert "empty_val_split" in response.json()["detail"]
    _assert_no_training_side_effects(app, storage)


def test_creates_lists_and_reloads_training_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.01)) as client:
        created = client.post("/api/training-runs", json=_request())
        assert created.status_code == 201
        run_id = created.json()["id"]
        assert created.json()["status"] == "running"
        assert client.get("/api/training-runs").json()[0]["id"] == run_id
        details = client.get(f"/api/training-runs/{run_id}/details")
        assert details.status_code == 200
        assert details.json()["configuration"]["epochs"] == 5

    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.01)) as client:
        assert client.get(f"/api/training-runs/{run_id}").status_code == 200


def test_refreshes_run_until_completed(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.01)) as client:
        run_id = client.post("/api/training-runs", json=_request()).json()["id"]
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            response = client.post(f"/api/training-runs/{run_id}/refresh")
            if response.json()["status"] == "completed":
                break
            time.sleep(0.02)
        assert response.json()["status"] == "completed"
        assert response.json()["progress"] == 100.0


def test_cancels_running_training_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.2)) as client:
        run_id = client.post("/api/training-runs", json=_request()).json()["id"]
        response = client.post(f"/api/training-runs/{run_id}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"


def test_rejects_task_mismatch(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    payload = _request() | {"task_type": "segment"}
    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.01)) as client:
        response = client.post("/api/training-runs", json=payload)
        assert response.status_code == 409


def test_persists_selected_dataset_classes_in_manifest(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    payload = _request() | {"selected_classes": ["light"], "class_aliases": {"light": "indicator"}}

    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.2)) as client:
        response = client.post("/api/training-runs", json=payload)
        manifest = json.loads((Path(response.json()["run_directory"]) / "manifest.json").read_text(encoding="utf-8"))
        client.post(f"/api/training-runs/{response.json()['id']}/cancel")

    assert response.status_code == 201
    assert manifest["spec"]["selected_classes"] == ["light"]
    assert manifest["spec"]["class_aliases"] == {"light": "indicator"}


def test_persists_advanced_augmentation_in_manifest_and_response(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    augmentation = {
        "mosaic": 0.8, "mixup": 0.1, "copy_paste": 0.2,
        "degrees": 8.0, "translate": 0.12, "scale": 0.4,
        "fliplr": 0.25, "hsv_h": 0.01, "hsv_s": 0.6, "hsv_v": 0.3,
    }

    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.2)) as client:
        response = client.post("/api/training-runs", json=_request() | {
            "preset_id": "custom",
            "augmentation": augmentation,
        })
        manifest = json.loads((Path(response.json()["run_directory"]) / "manifest.json").read_text(encoding="utf-8"))
        reloaded = client.get(f"/api/training-runs/{response.json()['id']}").json()
        client.post(f"/api/training-runs/{response.json()['id']}/cancel")

    assert response.status_code == 201
    assert response.json()["augmentation"] == augmentation
    assert reloaded["augmentation"] == augmentation
    assert manifest["spec"]["augmentation"] == augmentation


def test_rejects_class_not_present_in_dataset_task(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    payload = _request() | {"selected_classes": ["missing"]}

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.post("/api/training-runs", json=payload)

    assert response.status_code == 409


def test_serves_training_artifact_by_storage_relative_path(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    artifact_path = storage / "training-runs" / "training-preview" / "ultralytics" / "train_batch0.jpg"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"training-preview")
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        served = client.get("/api/artifacts", params={"path": "training-runs/training-preview/ultralytics/train_batch0.jpg"})
        rejected = client.get("/api/artifacts", params={"path": "../outside.jpg"})

    assert served.status_code == 200
    assert served.content == b"training-preview"
    assert rejected.status_code == 403


def test_marks_missing_runner_interrupted_on_restart(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    repository = TrainingRunRepository(create_registry(storage / "registry" / "factory.db"))
    repository.create(
        TrainingRunSpec(
            name="orphaned run",
            task_type="detect",
            dataset_release_id="dataset-lights-1.0.0",
            base_model="yolo11n.pt",
            epochs=5,
            batch=2,
            image_size=640,
            device="cuda:0",
        ),
        run_id="training-orphaned",
    )
    repository.transition(
        "training-orphaned",
        "running",
        pid=999_999_999,
        run_directory=str(storage / "training-runs" / "training-orphaned"),
    )

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.get("/api/training-runs/training-orphaned")

    assert response.status_code == 200
    assert response.json()["status"] == "interrupted"
    assert response.json()["message"] == "Runner process is no longer available"


def test_failed_training_details_expose_diagnostic_without_fabricated_metrics(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    repository = TrainingRunRepository(create_registry(storage / "registry" / "factory.db"))
    repository.create(
        TrainingRunSpec("failed", "detect", "dataset-lights-1.0.0", "yolo11n.pt", 100, 1, 320, "cpu"),
        run_id="training-failed",
    )
    run_directory = storage / "training-runs" / "training-failed"
    run_directory.mkdir(parents=True)
    (run_directory / "progress.jsonl").write_text(json.dumps({
        "status": "running", "phase": "training", "progress": 78,
        "message": "Epoch 78", "epoch": 78, "total_epochs": 100,
    }) + "\n", encoding="utf-8")
    repository.transition(
        "training-failed", "running", run_directory=str(run_directory), phase="training",
    )
    repository.transition(
        "training-failed", "failed", exit_code=137, phase="training",
        message="Runner exited with code 137", epoch=78, total_epochs=100,
    )

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.get("/api/training-runs/training-failed/details")

    assert response.status_code == 200
    payload = response.json()
    assert payload["failure_diagnostic"]["code"] == "resource_limit"
    assert payload["failure_diagnostic"]["last_successful_epoch"] == 78
    assert payload["recovery_options"]["can_safe_retry"] is True
    assert payload["recovery_options"]["can_evaluate_best"] is False
    assert payload["latest_metrics"] == {}


def test_safe_retry_is_idempotent_and_preserves_failed_source(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    repository = TrainingRunRepository(create_registry(storage / "registry" / "factory.db"))
    source_spec = TrainingRunSpec(
        "failed CPU run", "detect", "dataset-lights-1.0.0", "yolo11n.pt",
        100, 2, 640, "cpu", selected_classes=("light",),
    )
    repository.create(source_spec, run_id="training-source")
    source_dir = storage / "training-runs" / "training-source"
    source_dir.mkdir(parents=True)
    best_weight = source_dir / "ultralytics" / "weights" / "best.pt"
    best_weight.parent.mkdir(parents=True)
    best_weight.write_bytes(b"recoverable-best-weight")
    repository.transition("training-source", "running", run_directory=str(source_dir), phase="training")
    repository.transition("training-source", "failed", exit_code=137, phase="training")
    (source_dir / "failure.json").write_text(json.dumps({
        "code": "resource_limit",
        "recoverability": {"can_safe_retry": True, "can_evaluate_best": False},
    }), encoding="utf-8")
    request = {"strategy": "safe", "request_id": "44fd6bd8-9a22-4fe7-954b-31bc2c39e98f"}

    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.2)) as client:
        first = client.post("/api/training-runs/training-source/retry", json=request)
        second = client.post("/api/training-runs/training-source/retry", json=request)
        source = client.get("/api/training-runs/training-source")
        source_details = client.get("/api/training-runs/training-source/details")
        client.post(f"/api/training-runs/{first.json()['id']}/cancel")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert first.json()["batch"] == 1
    assert first.json()["image_size"] == 640
    assert source.json()["status"] == "failed"
    assert len(repository.related("training-source")) == 1
    assert source_details.json()["recovery_options"]["can_evaluate_best"] is True
    assert source_details.json()["related_runs"][0]["id"] == first.json()["id"]


def test_safe_retry_rejects_prerequisite_failure_without_creating_child(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    repository = TrainingRunRepository(create_registry(storage / "registry" / "factory.db"))
    repository.create(
        TrainingRunSpec("disk failure", "detect", "dataset-lights-1.0.0", "yolo11n.pt", 5, 1, 320, "cpu"),
        run_id="training-disk-failed",
    )
    run_directory = storage / "training-runs" / "training-disk-failed"
    run_directory.mkdir(parents=True)
    repository.transition("training-disk-failed", "running", run_directory=str(run_directory))
    repository.transition("training-disk-failed", "failed", exit_code=1)
    (run_directory / "failure.json").write_text(json.dumps({
        "code": "disk_full", "recoverability": {"can_safe_retry": False},
    }), encoding="utf-8")

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.post("/api/training-runs/training-disk-failed/retry", json={
            "strategy": "safe", "request_id": "request-disk-full",
        })

    assert response.status_code == 409
    assert "磁盘" in response.json()["detail"]
    assert repository.related("training-disk-failed") == []


def test_recovers_independent_evaluation_as_immutable_child_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    repository = TrainingRunRepository(create_registry(storage / "registry" / "factory.db"))
    repository.create(
        TrainingRunSpec(
            "recoverable", "detect", "dataset-lights-1.0.0", "yolo11n.pt",
            20, 1, 320, "cpu", selected_classes=("light",),
        ),
        run_id="training-recoverable",
    )
    source_dir = storage / "training-runs" / "training-recoverable"
    best = source_dir / "ultralytics" / "weights" / "best.pt"
    best.parent.mkdir(parents=True)
    best.write_bytes(b"best")
    repository.transition("training-recoverable", "running", run_directory=str(source_dir), phase="export")
    repository.transition("training-recoverable", "failed", exit_code=1, phase="export")

    with TestClient(create_app(storage_root=storage, training_engine="simulation", training_step_seconds=0.2)) as client:
        response = client.post("/api/training-runs/training-recoverable/recover-evaluation")
        source = client.get("/api/training-runs/training-recoverable")
        client.post(f"/api/training-runs/{response.json()['id']}/cancel")

    assert response.status_code == 201
    assert response.json()["source_run_id"] == "training-recoverable"
    assert response.json()["execution_mode"] == "evaluate_existing"
    assert response.json()["base_model"] == str(best.resolve())
    assert response.json()["dataset_release_id"] == "dataset-lights-1.0.0"
    assert response.json()["selected_classes"] == ["light"]
    assert response.json()["run_directory"] != str(source_dir)
    assert source.json()["status"] == "failed"


def test_deletes_terminal_training_run_but_preserves_artifacts_by_default(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    repository = TrainingRunRepository(create_registry(storage / "registry" / "factory.db"))
    repository.create(
        TrainingRunSpec("terminal", "detect", "dataset-lights-1.0.0", "yolo11n.pt", 1, 1, 320, "cpu"),
        run_id="training-terminal",
    )
    run_directory = storage / "training-runs" / "training-terminal"
    run_directory.mkdir(parents=True)
    repository.transition("training-terminal", "cancelled", run_directory=str(run_directory))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        response = client.delete("/api/training-runs/training-terminal")

        assert response.status_code == 204
        assert client.get("/api/training-runs/training-terminal").status_code == 404
        assert run_directory.is_dir()


def test_rejects_deleting_active_or_model_referenced_training_run(tmp_path: Path) -> None:
    storage = _storage(tmp_path)
    repository = TrainingRunRepository(create_registry(storage / "registry" / "factory.db"))
    repository.create(
        TrainingRunSpec("active", "detect", "dataset-lights-1.0.0", "yolo11n.pt", 1, 1, 320, "cpu"),
        run_id="training-active",
    )

    repository.create(
        TrainingRunSpec("referenced", "detect", "dataset-lights-1.0.0", "yolo11n.pt", 1, 1, 320, "cpu"),
        run_id="training-referenced",
    )
    repository.transition("training-referenced", "cancelled")
    registry = create_registry(storage / "registry" / "factory.db")
    from yolo_factory.registry.models import ModelVersionRecord
    with session_scope(registry) as session:
        session.add(ModelVersionRecord(
            id="model-referenced",
            name="referenced",
            version="1.0.0",
            task_type="detect",
            training_run_id="training-referenced",
            dataset_release_id="dataset-lights-1.0.0",
            config_json=json.dumps({"selected_classes": [], "class_aliases": {}, "pt_path": "best.pt", "metrics": {}}),
            status="candidate",
            gates_json="{}",
        ))

    with TestClient(create_app(storage_root=storage, training_engine="simulation")) as client:
        active = client.delete("/api/training-runs/training-active")
        referenced = client.delete("/api/training-runs/training-referenced")

    assert active.status_code == 409
    assert "active" in active.json()["detail"].lower()
    assert referenced.status_code == 409
    assert "model" in referenced.json()["detail"].lower()
