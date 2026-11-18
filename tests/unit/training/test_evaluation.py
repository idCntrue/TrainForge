import json
from pathlib import Path
from types import SimpleNamespace

from yolo_factory.training.evaluation import normalize_test_metrics, write_test_metrics


def _metrics(p, r, ap50, ap, class_ids):
    return SimpleNamespace(p=p, r=r, ap50=ap50, ap=ap, ap_class_index=class_ids)


def test_normalizes_segment_overall_and_per_class_metrics() -> None:
    result = SimpleNamespace(
        results_dict={
            "metrics/precision(M)": 0.81, "metrics/recall(M)": 0.74,
            "metrics/mAP50(M)": 0.69, "metrics/mAP50-95(M)": 0.52,
            "metrics/precision(B)": 0.77, "metrics/recall(B)": 0.71,
            "metrics/mAP50(B)": 0.66, "metrics/mAP50-95(B)": 0.48,
        },
        seg=_metrics(
            p=[0.81, 0.62], r=[0.74, 0.58], ap50=[0.69, 0.55], ap=[0.48, 0.40],
            class_ids=[0, 1],
        ),
    )

    report = normalize_test_metrics(result, task_type="segment", class_names=["sign", "light"])

    assert report["split"] == "test"
    assert report["overall"]["map50_95_mask"] == 0.52
    assert report["per_class"][0] == {
        "class_id": 0, "class_name": "sign", "precision": 0.81,
        "recall": 0.74, "map50": 0.69, "map50_95": 0.48,
    }


def test_absent_class_does_not_shift_later_rows() -> None:
    """A class missing from the test split must not shift every row after it.

    Ultralytics aligns p/r/ap50/ap with ap_class_index (present classes only),
    while maps is a full nc array with the global mean filled in for absent
    classes. Indexing by class id produced rows like map50=0.083 with
    map50_95=0.568 (the global mean) on a real run.
    """
    class_names = ["a", "b", "c", "absent", "e", "f", "g"]
    result = SimpleNamespace(
        results_dict={"metrics/mAP50(M)": 0.5, "metrics/mAP50-95(M)": 0.4},
        seg=SimpleNamespace(
            p=[0.9, 0.8, 0.7, 0.6, 0.5, 0.4],
            r=[0.9, 0.8, 0.7, 0.6, 0.5, 0.4],
            ap50=[0.95, 0.85, 0.75, 0.65, 0.55, 0.45],
            ap=[0.92, 0.82, 0.72, 0.62, 0.52, 0.42],
            maps=[0.92, 0.82, 0.72, 0.4, 0.62, 0.52, 0.42],
            ap_class_index=[0, 1, 2, 4, 5, 6],
        ),
    )

    report = normalize_test_metrics(result, task_type="segment", class_names=class_names)

    rows = {row["class_name"]: row for row in report["per_class"]}
    assert rows["absent"] == {
        "class_id": 3, "class_name": "absent",
        "precision": None, "recall": None, "map50": None, "map50_95": None,
    }
    assert rows["e"]["map50"] == 0.65
    assert rows["e"]["map50_95"] == 0.62
    assert rows["g"]["map50"] == 0.45
    for row in report["per_class"]:
        if row["map50"] is not None and row["map50_95"] is not None:
            assert row["map50_95"] <= row["map50"]


def test_missing_metrics_stay_null_and_report_is_atomic(tmp_path: Path) -> None:
    report = normalize_test_metrics(SimpleNamespace(results_dict={}), task_type="detect", class_names=["a"])
    path = write_test_metrics(tmp_path / "test-metrics.json", report)

    assert report["overall"]["precision"] is None
    assert json.loads(path.read_text(encoding="utf-8"))["overall"]["map50_95"] is None
    assert not (tmp_path / "test-metrics.json.tmp").exists()
