from yolo_factory.training.quality_report import build_quality_report


def _metrics(precision=0.85, recall=0.84, strict_map=0.55):
    return {
        "overall": {
            "precision": precision, "recall": recall,
            "map50_95_mask": strict_map, "map50_95_box": strict_map,
        },
        "per_class": [{"class_name": "sign", "map50_95": strict_map}],
    }


def test_refuses_to_grade_insufficient_test_evidence() -> None:
    report = build_quality_report(
        task_type="segment",
        dataset_quality={
            "split_images": {"test": 8},
            "class_instances": {"sign": {"test": 8}},
        },
        test_metrics=_metrics(0.95, 0.95, 0.90),
        best_epoch=42,
    )

    assert report["verdict"] == "insufficient_evidence"
    assert report["confidence"] == "low"


def test_marks_reliable_balanced_model_ready() -> None:
    report = build_quality_report(
        task_type="detect",
        dataset_quality={
            "split_images": {"test": 40},
            "class_instances": {"sign": {"test": 20}, "light": {"test": 20}},
        },
        test_metrics=_metrics(),
        best_epoch=84,
    )

    assert report["verdict"] == "ready"
    assert report["confidence"] == "high"
    assert report["best_epoch"] == 84


def test_distinguishes_trial_from_needs_improvement() -> None:
    evidence = {
        "split_images": {"test": 40},
        "class_instances": {"sign": {"test": 40}},
    }
    assert build_quality_report("detect", evidence, _metrics(0.65, 0.65, 0.35), 10)["verdict"] == "trial"
    assert build_quality_report("detect", evidence, _metrics(0.4, 0.5, 0.2), 10)["verdict"] == "needs_improvement"

