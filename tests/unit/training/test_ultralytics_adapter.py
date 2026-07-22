from pathlib import Path

import pytest
import yaml

from yolo_factory.training.resource_policy import TrainingResourcePolicy
from yolo_factory.training.ultralytics_adapter import (
    TrainingMemoryPressure,
    ensure_training_memory_available,
    prepare_dataset_view,
    run_ultralytics,
)


GIB = 1024 ** 3


def test_rejects_low_windows_memory_before_next_epoch() -> None:
    policy = TrainingResourcePolicy()

    with pytest.raises(TrainingMemoryPressure, match="提交内存"):
        ensure_training_memory_available(policy, {
            "windows_available_commit_bytes": 3 * GIB,
            "windows_available_physical_bytes": 5 * GIB,
            "windows_leaspac_process_count": 30,
            "windows_leaspac_private_bytes": 31 * GIB,
        })


def test_accepts_safe_windows_memory_before_next_epoch() -> None:
    ensure_training_memory_available(TrainingResourcePolicy(), {
        "windows_available_commit_bytes": 12 * GIB,
        "windows_available_physical_bytes": 6 * GIB,
    })


def test_accepts_normal_physical_memory_drop_after_model_loading() -> None:
    ensure_training_memory_available(TrainingResourcePolicy(), {
        "windows_available_commit_bytes": 12 * GIB,
        "windows_available_physical_bytes": int(3.49 * GIB),
    })


def test_accepts_linux_memory_snapshot_before_next_epoch() -> None:
    ensure_training_memory_available(TrainingResourcePolicy(), {
        "memory_current_bytes": 2 * GIB,
        "memory_limit_bytes": 8 * GIB,
    })


def test_reports_memory_pressure_when_one_windows_metric_is_unavailable() -> None:
    with pytest.raises(TrainingMemoryPressure, match="可用物理内存 未知"):
        ensure_training_memory_available(TrainingResourcePolicy(), {
            "windows_available_commit_bytes": 3 * GIB,
            "windows_available_physical_bytes": None,
        })


def _dataset(root: Path) -> Path:
    for split in ("train", "val", "test"):
        images = root / split / "images"
        labels = root / split / "labels"
        images.mkdir(parents=True)
        labels.mkdir(parents=True)
        (images / "sample.jpg").write_bytes(b"image")
        (labels / "sample.txt").write_text("0 0.5 0.5 0.2 0.2\n2 0.4 0.4 0.1 0.1\n", encoding="utf-8")
    data_yaml = root / "data.yaml"
    data_yaml.write_text(yaml.safe_dump({"path": ".", "train": "train/images", "val": "val/images", "test": "test/images", "names": ["a", "b", "c"]}), encoding="utf-8")
    return data_yaml


def test_prepares_class_subset_without_modifying_release(tmp_path: Path) -> None:
    source_yaml = _dataset(tmp_path / "release")

    derived_yaml = prepare_dataset_view(
        source_yaml,
        tmp_path / "run",
        selected_classes=["c", "a"],
        class_aliases={"c": "renamed-c"},
    )

    payload = yaml.safe_load(derived_yaml.read_text(encoding="utf-8"))
    assert payload["names"] == ["renamed-c", "a"]
    assert (derived_yaml.parent / "train" / "labels" / "sample.txt").read_text(encoding="utf-8").splitlines() == [
        "1 0.5 0.5 0.2 0.2",
        "0 0.4 0.4 0.1 0.1",
    ]
    assert (source_yaml.parent / "train" / "labels" / "sample.txt").read_text(encoding="utf-8").startswith("0 ")


def test_prepare_dataset_view_ignores_non_image_files_and_accepts_uppercase_extensions(tmp_path: Path) -> None:
    source_yaml = _dataset(tmp_path / "release")
    train_images = source_yaml.parent / "train" / "images"
    (train_images / "valid.PNG").write_bytes(b"image")
    (train_images / "Thumbs.db").write_bytes(b"metadata")
    (train_images / ".gitkeep").write_text("", encoding="utf-8")

    derived_yaml = prepare_dataset_view(
        source_yaml,
        tmp_path / "run",
        selected_classes=[],
        class_aliases={},
    )

    copied = {path.name for path in (derived_yaml.parent / "train" / "images").iterdir()}
    assert copied == {"sample.jpg", "valid.PNG"}


def test_runs_ultralytics_with_normalized_progress_metrics_and_artifacts(tmp_path: Path) -> None:
    source_yaml = _dataset(tmp_path / "release")
    run_directory = tmp_path / "run"
    weights = run_directory / "ultralytics" / "weights"
    weights.mkdir(parents=True)
    (weights / "best.pt").write_bytes(b"best")
    (weights / "last.pt").write_bytes(b"last")
    events: list[dict] = []

    class Metrics:
        results_dict = {
            "metrics/precision(B)": 0.8,
            "metrics/recall(B)": 0.7,
            "metrics/mAP50(B)": 0.9,
            "metrics/precision(M)": 0.75,
            "metrics/recall(M)": 0.65,
            "metrics/mAP50(M)": 0.85,
        }

    class Trainer:
        epoch = 0
        epochs = 2

    class FakeModel:
        def __init__(self) -> None:
            self.callbacks = {}
            self.trainer = type("TrainerState", (), {"best": weights / "best.pt", "last": weights / "last.pt"})()
            self.train_kwargs = None

        def add_callback(self, name, callback):
            self.callbacks[name] = callback

        def train(self, **kwargs):
            self.train_kwargs = kwargs
            trainer = Trainer()
            for epoch in range(2):
                trainer.epoch = epoch
                results_csv = run_directory / "ultralytics" / "results.csv"
                if epoch == 0:
                    results_csv.write_text(
                        "epoch,metrics/mAP50-95(M)\n1,0.7\n", encoding="utf-8",
                    )
                else:
                    results_csv.write_text(
                        "epoch,metrics/mAP50-95(M)\n1,0.7\n2,0.6\n", encoding="utf-8",
                    )
                self.callbacks["on_fit_epoch_end"](trainer)

    model = FakeModel()
    class ValidationModel:
        def __init__(self) -> None:
            self.val_kwargs = None

        def val(self, **kwargs):
            self.val_kwargs = kwargs
            return Metrics()

    validation_model = ValidationModel()

    class TestModel:
        def __init__(self) -> None:
            self.val_kwargs = None

        def val(self, **kwargs):
            self.val_kwargs = kwargs
            return Metrics()

    test_model = TestModel()
    factory_calls = []

    def factory(weight):
        factory_calls.append(str(weight))
        return [model, validation_model, test_model][len(factory_calls) - 1]
    manifest = {
        "run_id": "run-001",
        "spec": {
            "task_type": "segment",
            "base_model": "yolo11n-seg.pt",
            "epochs": 2,
            "batch": 1,
            "image_size": 320,
            "device": "cpu",
            "selected_classes": ["a", "b", "c"],
            "class_aliases": {},
            "preset_id": "cpu-balanced",
            "patience": 25,
            "optimizer": "auto",
            "close_mosaic": 10,
            "augment_profile": "conservative",
            "augmentation": {
                "mosaic": 0.8,
                "mixup": 0.1,
                "copy_paste": 0.2,
                "degrees": 8.0,
                "translate": 0.12,
                "scale": 0.4,
                "fliplr": 0.25,
                "hsv_h": 0.01,
                "hsv_s": 0.6,
                "hsv_v": 0.3,
            },
        },
        "dataset": {"data_yaml_path": str(source_yaml)},
        "execution": {"workers": 0, "cache": False, "cpu_threads": 4},
    }

    result = run_ultralytics(manifest, run_directory, events.append, yolo_factory=factory)

    assert model.train_kwargs == {
        "data": str(run_directory / "dataset" / "data.yaml"),
        "epochs": 2,
        "batch": 1,
        "imgsz": 320,
        "device": "cpu",
        "project": str(run_directory),
        "name": "ultralytics",
        "exist_ok": True,
        "workers": 0,
        "cache": False,
        "patience": 25,
        "optimizer": "auto",
        "close_mosaic": 10,
        "mosaic": 0.8,
        "mixup": 0.1,
        "copy_paste": 0.2,
        "degrees": 8.0,
        "translate": 0.12,
        "scale": 0.4,
        "fliplr": 0.25,
        "hsv_h": 0.01,
        "hsv_s": 0.6,
        "hsv_v": 0.3,
    }
    assert factory_calls[1].endswith("best.pt")
    assert validation_model.val_kwargs == {
        "data": str(run_directory / "dataset" / "data.yaml"),
        "device": "cpu",
        "batch": 1,
        "workers": 0,
    }
    assert factory_calls[2].endswith("best.pt")
    assert test_model.val_kwargs == {
        "data": str(run_directory / "dataset" / "data.yaml"),
        "split": "test",
        "batch": 1,
        "imgsz": 320,
        "device": "cpu",
        "workers": 0,
        "project": str(run_directory),
        "name": "test-evaluation",
        "plots": True,
    }
    assert (run_directory / "test-metrics.json").is_file()
    assert [event["epoch"] for event in events if event["phase"] == "training"] == [1, 2]
    assert result["metrics"]["precision"] == 0.75
    assert result["metrics"]["recall"] == 0.65
    assert result["metrics"]["map50"] == 0.85
    assert result["metrics"]["box_map50"] == 0.9
    assert result["metrics"]["mask_map50"] == 0.85
    assert result["artifacts"]["best_pt"].endswith("best.pt")
    completed = events[-1]
    assert completed["best_epoch"] == 1
    assert completed["completed_epochs"] == 2
    assert completed["stopped_early"] is False


def test_evaluate_existing_mode_never_calls_train(tmp_path: Path) -> None:
    source_yaml = _dataset(tmp_path / "release")
    run_directory = tmp_path / "recovery-run"
    best = tmp_path / "source-run" / "ultralytics" / "weights" / "best.pt"
    best.parent.mkdir(parents=True)
    best.write_bytes(b"best")
    events = []

    class Metrics:
        results_dict = {"metrics/mAP50-95(B)": 0.5}
        box = None

    class EvaluationModel:
        def train(self, **kwargs):
            raise AssertionError("evaluation recovery must not train")

        def val(self, **kwargs):
            assert kwargs["split"] == "test"
            return Metrics()

    result = run_ultralytics({
        "run_id": "recovery",
        "spec": {
            "task_type": "detect", "base_model": str(best), "epochs": 2,
            "batch": 1, "image_size": 320, "device": "cpu",
            "selected_classes": ["a", "b", "c"], "class_aliases": {},
            "execution_mode": "evaluate_existing",
        },
        "dataset": {"data_yaml_path": str(source_yaml)},
        "execution": {"workers": 0, "cache": False, "cpu_threads": 4},
    }, run_directory, events.append, yolo_factory=lambda _: EvaluationModel())

    assert result["test_metrics"]["overall"]["map50_95"] == 0.5
    assert events[-1]["status"] == "completed"
