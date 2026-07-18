from yolo_factory.training.recovery import plan_safe_retry


def test_resource_failure_reduces_batch_before_image_size() -> None:
    plan = plan_safe_retry(
        task_type="segment", device="cpu", batch=2, image_size=640,
        failure_code="resource_limit",
    )

    assert plan.allowed is True
    assert plan.batch == 1
    assert plan.image_size == 640
    assert plan.preset_id == "cpu-balanced"


def test_resource_failure_reduces_image_after_batch_reaches_one() -> None:
    plan = plan_safe_retry(
        task_type="segment", device="cpu", batch=1, image_size=640,
        failure_code="resource_limit",
    )

    assert plan.allowed is True
    assert plan.batch == 1
    assert plan.image_size == 512


def test_non_retryable_failure_requires_user_action() -> None:
    plan = plan_safe_retry(
        task_type="segment", device="cpu", batch=1, image_size=640,
        failure_code="disk_full",
    )

    assert plan.allowed is False
    assert "磁盘" in plan.reason

