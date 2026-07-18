MIN_TEST_IMAGES = 30
MIN_TEST_INSTANCES_PER_CLASS = 10
READY_PRECISION = 0.80
READY_RECALL = 0.80
READY_MAP50_95 = 0.50
TRIAL_PRECISION = 0.60
TRIAL_RECALL = 0.60
TRIAL_MAP50_95 = 0.30


def build_quality_report(
    task_type: str,
    dataset_quality: dict,
    test_metrics: dict | None,
    best_epoch: int | None,
) -> dict:
    test_images = int(dataset_quality.get("split_images", {}).get("test", 0))
    class_instances = dataset_quality.get("class_instances", {})
    weak_evidence = [
        name for name, splits in class_instances.items()
        if int(splits.get("test", 0)) < MIN_TEST_INSTANCES_PER_CLASS
    ]
    overall = (test_metrics or {}).get("overall", {})
    precision = overall.get("precision")
    recall = overall.get("recall")
    strict_key = "map50_95_mask" if task_type == "segment" else "map50_95_box"
    strict_map = overall.get(strict_key)
    reasons: list[str] = []
    recommendations: list[str] = []

    if test_images < MIN_TEST_IMAGES or weak_evidence or None in {precision, recall, strict_map}:
        verdict = "insufficient_evidence"
        confidence = "low"
        if test_images < MIN_TEST_IMAGES:
            reasons.append(f"独立测试图片仅 {test_images} 张，少于建议的 {MIN_TEST_IMAGES} 张")
        if weak_evidence:
            reasons.append("部分类别的独立测试实例少于 10 个: " + ", ".join(weak_evidence))
        if None in {precision, recall, strict_map}:
            reasons.append("独立测试指标不完整")
        recommendations.append("补充独立测试图片和各类别实例后重新评估")
    elif precision >= READY_PRECISION and recall >= READY_RECALL and strict_map >= READY_MAP50_95:
        verdict, confidence = "ready", "high"
        reasons.append("独立测试的准确率、召回率和严格综合精度均达到建议发布线")
        recommendations.append("结合真实业务样本复核后发布")
    elif precision >= TRIAL_PRECISION and recall >= TRIAL_RECALL and strict_map >= TRIAL_MAP50_95:
        verdict, confidence = "trial", "medium"
        reasons.append("达到试用线，但尚未达到建议发布线")
        recommendations.append("优先补充弱类别样本并复训")
    else:
        verdict, confidence = "needs_improvement", "high"
        reasons.append("至少一项独立测试核心指标低于试用线")
        recommendations.append("检查标注质量、类别平衡和错误样本后重新训练")

    weakest = sorted(
        (test_metrics or {}).get("per_class", []),
        key=lambda row: (row.get("map50_95") is None, row.get("map50_95") or 0),
    )[:5]
    return {
        "schema_version": 1,
        "verdict": verdict,
        "confidence": confidence,
        "reasons": reasons,
        "recommendations": recommendations,
        "best_epoch": best_epoch,
        "weakest_classes": weakest,
        "thresholds": {
            "min_test_images": MIN_TEST_IMAGES,
            "min_test_instances_per_class": MIN_TEST_INSTANCES_PER_CLASS,
            "ready": {"precision": READY_PRECISION, "recall": READY_RECALL, "map50_95": READY_MAP50_95},
            "trial": {"precision": TRIAL_PRECISION, "recall": TRIAL_RECALL, "map50_95": TRIAL_MAP50_95},
        },
    }
