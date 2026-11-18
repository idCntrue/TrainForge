from __future__ import annotations

import json
from pathlib import Path


def normalize_test_metrics(result, *, task_type: str, class_names: list[str]) -> dict:
    values = dict(getattr(result, "results_dict", {}) or {})
    prefix = "M" if task_type == "segment" else "B"
    overall = {
        "precision": _number(values.get(f"metrics/precision({prefix})")),
        "recall": _number(values.get(f"metrics/recall({prefix})")),
        "map50": _number(values.get(f"metrics/mAP50({prefix})")),
        "map50_95": _number(values.get(f"metrics/mAP50-95({prefix})")),
        "map50_box": _number(values.get("metrics/mAP50(B)")),
        "map50_95_box": _number(values.get("metrics/mAP50-95(B)")),
        "map50_mask": _number(values.get("metrics/mAP50(M)")),
        "map50_95_mask": _number(values.get("metrics/mAP50-95(M)")),
    }
    metrics = getattr(result, "seg" if task_type == "segment" else "box", None)
    columns = {
        "precision": _sequence(getattr(metrics, "p", None)),
        "recall": _sequence(getattr(metrics, "r", None)),
        "map50": _sequence(getattr(metrics, "ap50", None)),
        "map50_95": _mean_ap(metrics),
    }
    positions = _per_class_positions(metrics, len(class_names))
    per_class = []
    for class_id, class_name in enumerate(class_names):
        position = positions.get(class_id)
        per_class.append({
            "class_id": class_id,
            "class_name": class_name,
            **{
                name: _number(column[position]) if position is not None and position < len(column) else None
                for name, column in columns.items()
            },
        })
    return {
        "schema_version": 1,
        "split": "test",
        "task_type": task_type,
        "overall": overall,
        "per_class": per_class,
    }


def write_test_metrics(path: Path, report: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)
    return path


def _number(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean_ap(metrics) -> list:
    """Per-class mAP50-95 in ap_class_index order.

    ``Metric.maps`` is a full ``nc`` array indexed by class id, and classes with no
    evidence are filled with the global mean. ``Metric.ap`` is aligned with
    ``ap_class_index`` like p/r/ap50. Preferring ``ap`` keeps every column in one
    coordinate system; the mean-filled ``maps`` stays as a fallback for fakes that
    predate it.
    """
    values = _sequence(getattr(metrics, "ap", None))
    if values:
        return values
    return _sequence(getattr(metrics, "maps", None))


def _per_class_positions(metrics, class_count: int) -> dict[int, int]:
    """Map class id to its position in the per-class metric arrays.

    Ultralytics only reports classes that appear in the evaluated split, in
    ``ap_class_index`` order. Indexing those arrays by class id shifts every row
    after the first missing class (and makes mAP50-95 exceed mAP50), so resolve
    through ``ap_class_index`` whenever it is present.
    """
    class_ids = _sequence(getattr(metrics, "ap_class_index", None))
    if class_ids:
        return {int(class_id): position for position, class_id in enumerate(class_ids)}
    return {class_id: class_id for class_id in range(class_count)}


def _sequence(value) -> list:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    try:
        return list(value)
    except TypeError:
        return []
