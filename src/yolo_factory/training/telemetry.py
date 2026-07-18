import csv
from pathlib import Path


COLUMN_MAP = {
    "time": "time",
    "train/box_loss": "train_box_loss",
    "train/seg_loss": "train_seg_loss",
    "train/cls_loss": "train_cls_loss",
    "train/dfl_loss": "train_dfl_loss",
    "val/box_loss": "val_box_loss",
    "val/seg_loss": "val_seg_loss",
    "val/cls_loss": "val_cls_loss",
    "val/dfl_loss": "val_dfl_loss",
    "metrics/precision(B)": "precision_box",
    "metrics/recall(B)": "recall_box",
    "metrics/mAP50(B)": "map50_box",
    "metrics/mAP50-95(B)": "map50_95_box",
    "metrics/precision(M)": "precision_mask",
    "metrics/recall(M)": "recall_mask",
    "metrics/mAP50(M)": "map50_mask",
    "metrics/mAP50-95(M)": "map50_95_mask",
    "lr/pg0": "lr_pg0",
    "lr/pg1": "lr_pg1",
    "lr/pg2": "lr_pg2",
}


def parse_epoch_history(path: Path) -> list[dict[str, float | int]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, skipinitialspace=True)
        history = []
        for raw_row in reader:
            row = {(key or "").strip(): (value or "").strip() for key, value in raw_row.items()}
            if not row.get("epoch"):
                continue
            item: dict[str, float | int] = {"epoch": int(float(row["epoch"]))}
            for source, target in COLUMN_MAP.items():
                if row.get(source):
                    item[target] = float(row[source])
            history.append(item)
    return history


def select_best_epoch(history: list[dict[str, float | int]], task_type: str) -> int | None:
    metric = "map50_95_mask" if task_type == "segment" else "map50_95_box"
    candidates = [row for row in history if row.get(metric) is not None]
    if not candidates:
        return None
    return int(max(candidates, key=lambda row: float(row[metric]))["epoch"])
