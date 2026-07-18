import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task
from yolo_factory.training.details import build_training_details
from yolo_factory.training.models import TrainingRun, TrainingRunSpec


def test_builds_epoch_history_split_distribution_and_allowlisted_artifacts(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    run_dir = storage / "training-runs" / "run-1"
    output = run_dir / "ultralytics"
    (output / "weights").mkdir(parents=True)
    (output / "results.csv").write_text("epoch,time,train/box_loss\n1,3.5,1.2\n", encoding="utf-8")
    (output / "results.png").write_bytes(b"png")
    (output / "weights" / "best.pt").write_bytes(b"weights")
    (output / "secret.bin").write_bytes(b"secret")
    (run_dir / "runner.log").write_text("line-1\nline-2\n", encoding="utf-8")
    release_path = storage / "dataset-releases" / "task" / "dataset-v1.0.0"
    release_path.mkdir(parents=True)
    (release_path / "manifest.yaml").write_text(yaml.safe_dump({"requested_ratios": {"train": 70, "val": 20, "test": 10}, "actual_ratios": {"train": 70.0, "val": 20.0, "test": 10.0}, "split_counts": {"train": 7, "val": 2, "test": 1}}), encoding="utf-8")
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="task", task_type="detect", annotation_format="yolo-detect", classes_json='["a"]'))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="export", task_id="task", provider_project="native", provider_version="1", zip_path="x.zip", sha256="x"))
    with session_scope(registry) as session:
        session.add(DatasetRelease(id="release", task_id="task", annotation_export_id="export", version="1.0.0", release_path=release_path.relative_to(storage).as_posix(), status="published"))
    now = datetime.now(timezone.utc)
    run = TrainingRun(id="run-1", spec=TrainingRunSpec(name="run", task_type="detect", dataset_release_id="release", base_model="yolo11n.pt", epochs=10, batch=2, image_size=640, device="cuda:0"), status="running", progress=10, phase="training", message="Epoch 1", pid=None, run_directory=str(run_dir), heartbeat_at=None, created_at=now, updated_at=now, finished_at=None, exit_code=None, cancel_requested_at=None)

    details = build_training_details(run, storage, registry)

    assert details["epoch_history"] == [{"epoch": 1, "time": 3.5, "train_box_loss": 1.2}]
    assert details["split_distribution"]["split_counts"] == {"train": 7, "val": 2, "test": 1}
    assert {item["key"] for item in details["artifacts"]} == {"results", "best_pt", "runner_log", "results_csv"}
    assert details["logs"] == ["line-1", "line-2"]


def test_returns_persisted_failure_diagnostic_and_recovery_options(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    run_dir = storage / "training-runs" / "run-failed"
    run_dir.mkdir(parents=True)
    diagnostic = {
        "schema_version": 1,
        "code": "resource_limit",
        "summary": "训练进程被外部强制终止，通常与内存或容器资源限制有关",
        "action": "使用 CPU 安全配置重试，并降低图像尺寸或 Batch",
        "technical_message": "Runner exited with code 137",
        "exception_type": None,
        "traceback": None,
        "exit_code": 137,
        "failure_phase": "training",
        "failure_scope": "training",
        "last_successful_epoch": 78,
        "total_epochs": 100,
        "occurred_at": "2026-07-16T00:00:00+00:00",
        "evidence": ["process exit code 137 indicates an external SIGKILL"],
        "resource_snapshot": {},
        "recoverability": {
            "can_safe_retry": True,
            "can_evaluate_best": False,
            "best_weight_path": None,
            "preserved_artifact_count": 2,
            "reason": "需要重新运行训练",
        },
    }
    (run_dir / "failure.json").write_text(json.dumps(diagnostic, ensure_ascii=False), encoding="utf-8")
    registry, run = _failed_run_fixture(storage, run_dir, exit_code=137)

    details = build_training_details(run, storage, registry)

    assert details["failure_diagnostic"] == diagnostic
    assert details["recovery_options"]["can_safe_retry"] is True
    assert details["recovery_options"]["can_evaluate_best"] is False
    assert details["latest_metrics"] == {}
    assert "failure_diagnostic" in {artifact["key"] for artifact in details["artifacts"]}


def test_classifies_historical_failure_in_memory_without_writing_file(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    run_dir = storage / "training-runs" / "run-historical"
    run_dir.mkdir(parents=True)
    registry, run = _failed_run_fixture(storage, run_dir, exit_code=-9)

    details = build_training_details(run, storage, registry)

    assert details["failure_diagnostic"]["code"] == "resource_limit"
    assert details["failure_diagnostic"]["exit_code"] == -9
    assert not (run_dir / "failure.json").exists()


def test_catalogs_independent_test_metrics_and_images_with_test_prefix(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    run_dir = storage / "training-runs" / "run-test-artifacts"
    test_output = run_dir / "test-evaluation"
    test_output.mkdir(parents=True)
    (run_dir / "test-metrics.json").write_text("{}", encoding="utf-8")
    (test_output / "confusion_matrix.png").write_bytes(b"png")
    (test_output / "val_batch0_pred.jpg").write_bytes(b"jpg")
    registry, run = _failed_run_fixture(storage, run_dir, exit_code=1)

    details = build_training_details(run, storage, registry)

    keys = {artifact["key"] for artifact in details["artifacts"]}
    assert {"test_metrics", "test_confusion_matrix", "test_val_batch0_pred"}.issubset(keys)


def _failed_run_fixture(storage: Path, run_dir: Path, *, exit_code: int):
    registry = create_registry(storage / "registry" / "factory.db")
    with session_scope(registry) as session:
        session.add(Task(id="failed-task", task_type="detect", annotation_format="yolo-detect", classes_json='["a"]'))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="failed-export", task_id="failed-task", provider_project="native", provider_version="1", zip_path="x.zip", sha256="x"))
    with session_scope(registry) as session:
        session.add(DatasetRelease(id="failed-release", task_id="failed-task", annotation_export_id="failed-export", version="1.0.0", release_path="missing", status="published"))
    now = datetime.now(timezone.utc)
    run = TrainingRun(
        id=run_dir.name,
        spec=TrainingRunSpec("failed", "detect", "failed-release", "yolo11n.pt", 100, 1, 320, "cpu"),
        status="failed", progress=78, phase="training", message="Runner exited", pid=None,
        run_directory=str(run_dir), heartbeat_at=None, created_at=now, updated_at=now,
        finished_at=now, exit_code=exit_code, cancel_requested_at=None, epoch=78,
        total_epochs=100,
    )
    return registry, run
