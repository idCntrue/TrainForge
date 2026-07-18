from pathlib import Path

from yolo_factory.training.telemetry import parse_epoch_history, select_best_epoch


def test_parses_ultralytics_segmentation_epoch_metrics(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    csv_path.write_text(
        "epoch,time,train/box_loss,train/seg_loss,val/box_loss,val/seg_loss,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B),metrics/precision(M),metrics/recall(M),metrics/mAP50(M),metrics/mAP50-95(M),lr/pg0\n"
        "1,12.5,1.2,2.3,1.1,2.1,0.8,0.7,0.6,0.4,0.75,0.65,0.55,0.35,0.001\n",
        encoding="utf-8",
    )

    history = parse_epoch_history(csv_path)

    assert history == [{
        "epoch": 1, "time": 12.5, "train_box_loss": 1.2, "train_seg_loss": 2.3,
        "val_box_loss": 1.1, "val_seg_loss": 2.1, "precision_box": 0.8,
        "recall_box": 0.7, "map50_box": 0.6, "map50_95_box": 0.4,
        "precision_mask": 0.75, "recall_mask": 0.65, "map50_mask": 0.55,
        "map50_95_mask": 0.35, "lr_pg0": 0.001,
    }]


def test_omits_missing_or_blank_metrics(tmp_path: Path) -> None:
    csv_path = tmp_path / "results.csv"
    csv_path.write_text("epoch,time,train/box_loss\n1,,1.2\n", encoding="utf-8")
    assert parse_epoch_history(csv_path) == [{"epoch": 1, "train_box_loss": 1.2}]
    assert parse_epoch_history(tmp_path / "missing.csv") == []


def test_selects_best_epoch_using_task_specific_strict_map() -> None:
    history = [
        {"epoch": 1, "map50_95_box": 0.4, "map50_95_mask": 0.6},
        {"epoch": 2, "map50_95_box": 0.7, "map50_95_mask": 0.5},
    ]

    assert select_best_epoch(history, "detect") == 2
    assert select_best_epoch(history, "segment") == 1
    assert select_best_epoch([], "segment") is None
