import os
import json
import shutil
from pathlib import Path
from typing import Callable

import yaml

from yolo_factory.training.telemetry import parse_epoch_history, select_best_epoch
from yolo_factory.training.evaluation import normalize_test_metrics, write_test_metrics
from yolo_factory.training.quality_report import build_quality_report
from yolo_factory.datasets.quality import analyze_dataset_quality
from yolo_factory.datasets.validation import IMAGE_EXTENSIONS
from yolo_factory.training.resource_policy import (
    InsufficientTrainingMemory,
    TrainingResourcePolicy,
)
from yolo_factory.training.resource_snapshot import read_training_memory_snapshot


EventEmitter = Callable[[dict], None]


class TrainingMemoryPressure(RuntimeError):
    """Raised between epochs before Windows memory pressure reaches native code."""


def ensure_training_memory_available(
    policy: TrainingResourcePolicy,
    snapshot: dict[str, int | None],
) -> None:
    try:
        policy.validate_memory_snapshot(snapshot)
    except InsufficientTrainingMemory as exc:
        detail = exc.as_detail()
        commit = detail.get("available_commit_gib")
        physical = detail.get("available_physical_gib")
        commit_label = "未知" if commit is None else f"{commit:.2f} GiB"
        physical_label = "未知" if physical is None else f"{physical:.2f} GiB"
        raise TrainingMemoryPressure(
            "Windows 内存压力过高，训练已在下一轮开始前安全停止："
            f"剩余提交内存 {commit_label}，可用物理内存 {physical_label}"
        ) from exc


def _write_report(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)


def _persist_quality_reports(
    run_directory: Path, data_yaml: Path, spec: dict, test_report: dict | None,
    *, best_epoch: int | None,
) -> dict:
    class_names = _class_names(yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {})
    dataset_report = analyze_dataset_quality(data_yaml.parent, class_names=class_names).model_dump()
    quality_report = build_quality_report(spec["task_type"], dataset_report, test_report, best_epoch)
    _write_report(run_directory / "dataset-quality.json", dataset_report)
    _write_report(run_directory / "quality-report.json", quality_report)
    return quality_report


def _class_names(payload: dict) -> list[str]:
    names = payload.get("names", [])
    if isinstance(names, dict):
        return [names[index] for index in sorted(names)]
    return list(names)


def _link_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def prepare_dataset_view(
    source_yaml: Path,
    run_directory: Path,
    *,
    selected_classes: list[str],
    class_aliases: dict[str, str],
) -> Path:
    source_yaml = source_yaml.resolve()
    source_payload = yaml.safe_load(source_yaml.read_text(encoding="utf-8"))
    source_root = (source_yaml.parent / source_payload.get("path", ".")).resolve()
    source_names = _class_names(source_payload)
    selected = selected_classes or source_names
    if len(set(selected)) != len(selected) or any(name not in source_names for name in selected):
        raise ValueError("selected classes must be unique and present in the dataset")
    index_map = {source_names.index(name): target_index for target_index, name in enumerate(selected)}
    derived_root = run_directory / "dataset"

    for split in ("train", "val", "test"):
        images_value = source_payload.get(split)
        if not images_value:
            continue
        source_images = (source_root / images_value).resolve()
        source_labels = source_images.parent / "labels"
        derived_images = derived_root / split / "images"
        derived_labels = derived_root / split / "labels"
        derived_images.mkdir(parents=True, exist_ok=True)
        derived_labels.mkdir(parents=True, exist_ok=True)
        for image_path in source_images.iterdir():
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                _link_or_copy(image_path, derived_images / image_path.name)
                label_path = source_labels / f"{image_path.stem}.txt"
                if label_path.is_file():
                    lines: list[str] = []
                    for line in label_path.read_text(encoding="utf-8").splitlines():
                        parts = line.split()
                        if not parts:
                            continue
                        source_index = int(parts[0])
                        if source_index in index_map:
                            lines.append(" ".join([str(index_map[source_index]), *parts[1:]]))
                    (derived_labels / label_path.name).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    derived_payload = {
        "path": str(derived_root.resolve()),
        "train": "train/images",
        "val": "val/images",
        "names": [class_aliases.get(name, name) for name in selected],
        "nc": len(selected),
    }
    if source_payload.get("test"):
        derived_payload["test"] = "test/images"
    derived_yaml = derived_root / "data.yaml"
    derived_yaml.write_text(yaml.safe_dump(derived_payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return derived_yaml


def _validate_model(task_type: str, base_model: str) -> None:
    if task_type not in {"detect", "segment"}:
        raise ValueError(f"unsupported Ultralytics task: {task_type}")
    is_segment_model = "-seg" in Path(base_model).stem
    if task_type == "segment" and not is_segment_model:
        raise ValueError("segment training requires a segmentation base model")
    if task_type == "detect" and is_segment_model:
        raise ValueError("detect training requires a detection base model")


def _metric(results: dict, *keys: str) -> float | None:
    for key in keys:
        if key in results:
            return float(results[key])
    return None


def _validation_metrics(results: dict, task_type: str) -> dict[str, float | None]:
    prefix = "M" if task_type == "segment" else "B"
    return {
        "precision": _metric(results, f"metrics/precision({prefix})"),
        "recall": _metric(results, f"metrics/recall({prefix})"),
        "map50": _metric(results, f"metrics/mAP50({prefix})"),
        "box_precision": _metric(results, "metrics/precision(B)"),
        "box_recall": _metric(results, "metrics/recall(B)"),
        "box_map50": _metric(results, "metrics/mAP50(B)"),
        "mask_precision": _metric(results, "metrics/precision(M)"),
        "mask_recall": _metric(results, "metrics/recall(M)"),
        "mask_map50": _metric(results, "metrics/mAP50(M)"),
    }


def run_ultralytics(
    manifest: dict,
    run_directory: Path,
    emit: EventEmitter,
    *,
    yolo_factory=None,
) -> dict:
    spec = manifest["spec"]
    execution = manifest["execution"]
    evaluation_only = spec.get("execution_mode") == "evaluate_existing"
    if not evaluation_only:
        _validate_model(spec["task_type"], spec["base_model"])
    source_yaml = Path(manifest["dataset"]["data_yaml_path"])
    data_yaml = prepare_dataset_view(
        source_yaml,
        run_directory,
        selected_classes=list(spec.get("selected_classes", [])),
        class_aliases=dict(spec.get("class_aliases", {})),
    )
    if yolo_factory is None:
        from ultralytics import YOLO

        yolo_factory = YOLO
    model = yolo_factory(spec["base_model"])
    if evaluation_only:
        weight = Path(spec["base_model"])
        if not weight.is_file() or weight.stat().st_size == 0:
            raise FileNotFoundError(f"base model unavailable: {weight}")
        emit({"status": "evaluating", "phase": "test_evaluation", "progress": 75.0, "message": "Evaluating preserved best weights"})
        result = model.val(
            data=str(data_yaml), split="test", batch=spec["batch"],
            imgsz=spec["image_size"], device=spec["device"], workers=execution["workers"],
            project=str(run_directory), name="test-evaluation", plots=True,
        )
        class_names = _class_names(yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {})
        report = normalize_test_metrics(result, task_type=spec["task_type"], class_names=class_names)
        report_path = write_test_metrics(run_directory / "test-metrics.json", report)
        quality_report = _persist_quality_reports(run_directory, data_yaml, spec, report, best_epoch=None)
        artifacts = {"best_pt": str(weight.resolve()), "last_pt": None, "test_metrics": str(report_path.resolve())}
        artifacts.update({
            "dataset_quality": str((run_directory / "dataset-quality.json").resolve()),
            "quality_report": str((run_directory / "quality-report.json").resolve()),
        })
        emit({"status": "exporting", "phase": "artifacts", "progress": 90.0, "message": "Registering recovered evaluation", "artifacts": artifacts})
        emit({"status": "verifying", "phase": "verification", "progress": 97.0, "message": "Recovered evaluation verified", "artifacts": artifacts})
        emit({"status": "completed", "phase": "completed", "progress": 100.0, "message": "Independent evaluation completed", "metrics": report["overall"], "artifacts": artifacts})
        return {"metrics": report["overall"], "test_metrics": report, "quality_report": quality_report, "artifacts": artifacts, "data_yaml": str(data_yaml)}

    previous_elapsed = 0.0
    resource_policy = TrainingResourcePolicy.from_environment(os.environ)

    def on_train_epoch_start(trainer) -> None:
        del trainer
        ensure_training_memory_available(resource_policy, read_training_memory_snapshot())

    def on_fit_epoch_end(trainer) -> None:
        nonlocal previous_elapsed
        epoch = int(trainer.epoch) + 1
        epochs = int(trainer.epochs)
        history = parse_epoch_history(run_directory / "ultralytics" / "results.csv")
        latest = history[-1] if history else {"epoch": epoch}
        elapsed = float(latest.get("time", previous_elapsed))
        epoch_seconds = max(0.0, elapsed - previous_elapsed) if elapsed else None
        previous_elapsed = elapsed
        eta_seconds = (elapsed / epoch * (epochs - epoch)) if elapsed and epoch else None
        emit({
            "status": "running",
            "phase": "training",
            "progress": round(epoch / epochs * 70, 2),
            "message": f"Epoch {epoch}/{epochs} completed",
            "epoch": epoch,
            "total_epochs": epochs,
            "epoch_metrics": latest,
            "epoch_seconds": epoch_seconds,
            "eta_seconds": eta_seconds,
        })

    model.add_callback("on_train_epoch_start", on_train_epoch_start)
    model.add_callback("on_fit_epoch_end", on_fit_epoch_end)
    train_options = {
        "data": str(data_yaml),
        "epochs": spec["epochs"],
        "batch": spec["batch"],
        "imgsz": spec["image_size"],
        "device": spec["device"],
        "project": str(run_directory),
        "name": "ultralytics",
        "exist_ok": True,
        "workers": execution["workers"],
        "cache": execution["cache"],
        "patience": spec.get("patience", 20),
        "optimizer": spec.get("optimizer", "auto"),
        "close_mosaic": spec.get("close_mosaic", 10),
    }
    if spec.get("augment_profile") == "conservative":
        train_options.update({
            "fliplr": 0.0,
            "degrees": 5.0,
            "translate": 0.1,
            "scale": 0.3,
        })
    train_options.update(spec.get("augmentation") or {})
    model.train(
        **train_options,
    )
    trainer = getattr(model, "trainer", None)
    best = Path(getattr(trainer, "best", "")) if trainer is not None else Path()
    last = Path(getattr(trainer, "last", "")) if trainer is not None else Path()
    artifacts = {
        "best_pt": str(best.resolve()) if best.is_file() else None,
        "last_pt": str(last.resolve()) if last.is_file() else None,
    }
    if not artifacts["best_pt"]:
        raise RuntimeError("Ultralytics training did not produce best.pt")

    emit({"status": "evaluating", "phase": "evaluation", "progress": 80.0, "message": "Running validation"})
    validation_model = yolo_factory(artifacts["best_pt"])
    validation = validation_model.val(
        data=str(data_yaml),
        device=spec["device"],
        batch=spec["batch"],
        workers=execution["workers"],
    )
    results = dict(getattr(validation, "results_dict", {}))
    metrics = _validation_metrics(results, spec["task_type"])
    test_report = None
    test_images = data_yaml.parent / "test" / "images"
    if test_images.is_dir() and any(path.is_file() for path in test_images.iterdir()):
        emit({"status": "evaluating", "phase": "test_evaluation", "progress": 98.0, "message": "Evaluating best weights on independent test split"})
        test_model = yolo_factory(artifacts["best_pt"])
        test_result = test_model.val(
            data=str(data_yaml),
            split="test",
            batch=spec["batch"],
            imgsz=spec["image_size"],
            device=spec["device"],
            workers=execution["workers"],
            project=str(run_directory),
            name="test-evaluation",
            plots=True,
        )
        class_names = _class_names(yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {})
        test_report = normalize_test_metrics(test_result, task_type=spec["task_type"], class_names=class_names)
        write_test_metrics(run_directory / "test-metrics.json", test_report)
        artifacts["test_metrics"] = str((run_directory / "test-metrics.json").resolve())
    else:
        emit({"status": "evaluating", "phase": "test_evaluation", "progress": 98.0, "message": "Independent test evaluation unavailable", "evaluation_unavailable": True})
    emit({"status": "exporting", "phase": "artifacts", "progress": 99.0, "message": "Registering PT artifacts", "metrics": metrics, "artifacts": artifacts})
    emit({"status": "verifying", "phase": "verification", "progress": 99.5, "message": "PT artifacts verified", "metrics": metrics, "artifacts": artifacts})
    history = parse_epoch_history(run_directory / "ultralytics" / "results.csv")
    completed_epochs = int(history[-1]["epoch"]) if history else 0
    best_epoch = select_best_epoch(history, spec["task_type"])
    quality_report = _persist_quality_reports(
        run_directory, data_yaml, spec, test_report, best_epoch=best_epoch,
    )
    artifacts.update({
        "dataset_quality": str((run_directory / "dataset-quality.json").resolve()),
        "quality_report": str((run_directory / "quality-report.json").resolve()),
    })
    emit({
        "status": "completed", "phase": "completed", "progress": 100.0,
        "message": "Training and validation completed", "metrics": metrics,
        "artifacts": artifacts,
        "best_epoch": best_epoch,
        "completed_epochs": completed_epochs,
        "stopped_early": completed_epochs < int(spec["epochs"]),
    })
    return {"metrics": metrics, "test_metrics": test_report, "quality_report": quality_report, "artifacts": artifacts, "data_yaml": str(data_yaml)}
