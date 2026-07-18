import json
from pathlib import Path

import yaml

from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import DatasetRelease, Task
from yolo_factory.common.task_metadata import decode_task_classes
from yolo_factory.training.models import TrainingRun
from yolo_factory.training.telemetry import parse_epoch_history
from yolo_factory.training.failure_diagnostics import classify_training_failure
from yolo_factory.training.repository import TrainingRunRepository


IMAGE_NAMES = {
    "results.png", "confusion_matrix.png", "confusion_matrix_normalized.png",
}
IMAGE_PREFIXES = ("Box", "Mask", "train_batch", "val_batch")
FILE_NAMES = {"results.csv", "args.yaml"}


def _artifact_key(path: Path) -> str:
    if path.name == "results.png": return "results"
    if path.name == "results.csv": return "results_csv"
    if path.name == "runner.log": return "runner_log"
    if path.name == "manifest.json": return "run_manifest"
    if path.name == "failure.json": return "failure_diagnostic"
    if path.name == "test-metrics.json": return "test_metrics"
    if path.name == "dataset-quality.json": return "dataset_quality"
    if path.name == "quality-report.json": return "quality_report"
    if path.name in {"best.pt", "last.pt"}: return path.stem + "_pt"
    return path.stem.lower()


def _catalog(run_directory: Path, storage_root: Path) -> list[dict]:
    candidates = [
        run_directory / "runner.log", run_directory / "manifest.json",
        run_directory / "failure.json", run_directory / "test-metrics.json",
        run_directory / "dataset-quality.json", run_directory / "quality-report.json",
    ]
    output = run_directory / "ultralytics"
    if output.is_dir():
        candidates.extend(path for path in output.iterdir() if path.name in IMAGE_NAMES or path.name in FILE_NAMES or path.name.startswith(IMAGE_PREFIXES))
        candidates.extend([output / "weights" / "best.pt", output / "weights" / "last.pt"])
    test_output = run_directory / "test-evaluation"
    if test_output.is_dir():
        candidates.extend(
            path for path in test_output.iterdir()
            if path.name in IMAGE_NAMES or path.name.startswith(("Box", "Mask", "val_batch"))
        )
    artifacts = []
    for path in candidates:
        if not path.is_file():
            continue
        resolved = path.resolve()
        try:
            relative = resolved.relative_to(storage_root.resolve()).as_posix()
        except ValueError:
            continue
        suffix = path.suffix.lower()
        key = _artifact_key(path)
        if path.parent == test_output and not key.startswith("test_"):
            key = "test_" + key
        artifacts.append({
            "key": key, "name": path.name,
            "kind": "image" if suffix in {".png", ".jpg", ".jpeg"} else "weight" if suffix == ".pt" else "file",
            "path": relative, "size_bytes": path.stat().st_size,
        })
    return sorted(artifacts, key=lambda item: (item["kind"], item["name"]))


def _events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def build_training_details(run: TrainingRun, storage_root: Path, registry: Registry) -> dict:
    run_directory = Path(run.run_directory).resolve() if run.run_directory else None
    history_by_epoch = {}
    events = _events(run_directory / "progress.jsonl") if run_directory else []
    if run_directory:
        for row in parse_epoch_history(run_directory / "ultralytics" / "results.csv"):
            history_by_epoch[row["epoch"]] = row
    for event in events:
        row = event.get("epoch_metrics")
        if row and row.get("epoch") is not None:
            history_by_epoch[int(row["epoch"])] = {**history_by_epoch.get(int(row["epoch"]), {}), **row}

    split_distribution = {"requested_ratios": None, "actual_ratios": {}, "split_counts": {}, "split_seed": None, "grouping_strategy": None}
    with session_scope(registry) as session:
        release = session.get(DatasetRelease, run.spec.dataset_release_id)
        release_task = session.get(Task, release.task_id) if release is not None else None
    if release is not None:
        manifest_path = storage_root / release.release_path / "manifest.yaml"
        if manifest_path.is_file():
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            for key in split_distribution:
                split_distribution[key] = manifest.get(key, split_distribution[key])

    logs = []
    if run_directory and (run_directory / "runner.log").is_file():
        logs = (run_directory / "runner.log").read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
    latest_event = events[-1] if events else {}
    failure_diagnostic = None
    recovery_options = None
    if run.status == "failed" and run_directory:
        failure_path = run_directory / "failure.json"
        if failure_path.is_file():
            try:
                failure_diagnostic = json.loads(failure_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                failure_diagnostic = None
        if failure_diagnostic is None:
            best_weight = run_directory / "ultralytics" / "weights" / "best.pt"
            best_weight_path = None
            if best_weight.is_file() and best_weight.stat().st_size > 0:
                try:
                    best_weight_path = best_weight.resolve().relative_to(storage_root.resolve()).as_posix()
                except ValueError:
                    best_weight_path = None
            diagnostic = classify_training_failure(
                exit_code=run.exit_code,
                message=latest_event.get("technical_message") or latest_event.get("message") or run.message,
                log_tail=logs,
                failure_phase=latest_event.get("phase") or run.phase,
                last_successful_epoch=latest_event.get("last_successful_epoch", latest_event.get("epoch", run.epoch)),
                total_epochs=latest_event.get("total_epochs", run.total_epochs or run.spec.epochs),
                best_weight_path=best_weight_path,
                preserved_artifact_count=sum(1 for path in run_directory.rglob("*") if path.is_file()),
                exception_type=latest_event.get("exception_type"),
                traceback=latest_event.get("traceback"),
                occurred_at=(run.finished_at or run.updated_at).isoformat(),
            )
            failure_diagnostic = diagnostic.model_dump()
        recovery = dict(failure_diagnostic.get("recoverability") or {})
        best_weight = run_directory / "ultralytics" / "weights" / "best.pt"
        best_weight_path = None
        weight_is_valid = best_weight.is_file() and best_weight.stat().st_size > 0
        if weight_is_valid:
            try:
                best_weight.resolve().relative_to(run_directory)
                best_weight_path = best_weight.resolve().relative_to(storage_root.resolve()).as_posix()
            except ValueError:
                weight_is_valid = False
        task_classes, _ = decode_task_classes(release_task.classes_json) if release_task is not None else ([], {})
        mapping_is_valid = (
            release is not None
            and release.status == "published"
            and release_task is not None
            and release_task.task_type == run.spec.task_type
            and bool(run.spec.selected_classes)
            and set(run.spec.selected_classes).issubset(task_classes)
        )
        can_evaluate = weight_is_valid and mapping_is_valid
        recovery.update({
            "can_safe_retry": recovery.get("can_safe_retry", failure_diagnostic.get("code") in {"resource_limit", "runner_failed"}),
            "can_evaluate_best": can_evaluate,
            "best_weight_path": best_weight_path if can_evaluate else None,
            "preserved_artifact_count": recovery.get("preserved_artifact_count", sum(1 for path in run_directory.rglob("*") if path.is_file())),
            "reason": (
                "可使用已保存的最佳权重继续独立评估"
                if can_evaluate else "缺少有效的最佳权重或不可变数据集/类别映射"
            ),
        })
        recovery_options = recovery
    related_runs = TrainingRunRepository(registry).related(run.id)
    def load_report(name: str):
        path = run_directory / name if run_directory else None
        if not path or not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return {
        "run_id": run.id,
        "configuration": {
            "name": run.spec.name, "task_type": run.spec.task_type, "dataset_release_id": run.spec.dataset_release_id,
            "base_model": run.spec.base_model, "epochs": run.spec.epochs, "batch": run.spec.batch,
            "image_size": run.spec.image_size, "device": run.spec.device,
            "selected_classes": list(run.spec.selected_classes), "class_aliases": run.spec.class_aliases,
        },
        "timing": {"epoch_seconds": latest_event.get("epoch_seconds"), "eta_seconds": latest_event.get("eta_seconds")},
        "split_distribution": split_distribution,
        "epoch_history": [history_by_epoch[key] for key in sorted(history_by_epoch)],
        "latest_metrics": run.metrics,
        "failure_diagnostic": failure_diagnostic,
        "recovery_options": recovery_options,
        "related_runs": [
            {
                "id": related.id,
                "status": related.status,
                "name": related.spec.name,
                "source_run_id": related.spec.source_run_id,
                "execution_mode": related.spec.execution_mode,
                "retry_strategy": related.spec.retry_strategy,
            }
            for related in related_runs
        ],
        "dataset_quality": load_report("dataset-quality.json"),
        "test_metrics": load_report("test-metrics.json"),
        "quality_report": load_report("quality-report.json"),
        "artifacts": _catalog(run_directory, storage_root) if run_directory else [],
        "logs": logs,
        "warnings": [] if history_by_epoch else ["暂未生成逐轮指标"],
    }
