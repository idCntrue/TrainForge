import json
from pathlib import Path
from types import SimpleNamespace

from yolo_factory.training.evaluation import normalize_test_metrics, write_test_metrics


def test_normalizes_segment_overall_and_per_class_metrics() -> None:
    result = SimpleNamespace(
        results_dict={
            "metrics/precision(M)": 0.81, "metrics/recall(M)": 0.74,
            "metrics/mAP50(M)": 0.69, "metrics/mAP50-95(M)": 0.52,
            "metrics/precision(B)": 0.77, "metrics/recall(B)": 0.71,
            "metrics/mAP50(B)": 0.66, "metrics/mAP50-95(B)": 0.48,
        },
        seg=SimpleNamespace(
            p=[0.81, 0.62], r=[0.74, 0.58], ap50=[0.69, 0.55], maps=[0.48, 0.40],
        ),
    )

    report = normalize_test_metrics(result, task_type="segment", class_names=["sign", "light"])

    assert report["split"] == "test"
    assert report["overall"]["map50_95_mask"] == 0.52
    assert report["per_class"][0] == {
        "class_id": 0, "class_name": "sign", "precision": 0.81,
        "recall": 0.74, "map50": 0.69, "map50_95": 0.48,
    }


def test_missing_metrics_stay_null_and_report_is_atomic(tmp_path: Path) -> None:
    report = normalize_test_metrics(SimpleNamespace(results_dict={}), task_type="detect", class_names=["a"])
    path = write_test_metrics(tmp_path / "test-metrics.json", report)

    assert report["overall"]["precision"] is None
    assert json.loads(path.read_text(encoding="utf-8"))["overall"]["map50_95"] is None
    assert not (tmp_path / "test-metrics.json.tmp").exists()
