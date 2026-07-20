from yolo_factory.training.failure_diagnostics import classify_training_failure


def _classify(**overrides):
    arguments = {
        "exit_code": 1,
        "message": "",
        "log_tail": [],
        "failure_phase": "training",
        "last_successful_epoch": None,
        "total_epochs": 100,
        "best_weight_path": None,
        "preserved_artifact_count": 0,
    }
    arguments.update(overrides)
    return classify_training_failure(**arguments)


def test_classifies_resource_kill_without_claiming_confirmed_oom() -> None:
    killed = _classify(
        exit_code=137,
        last_successful_epoch=78,
        preserved_artifact_count=4,
    )

    assert killed.code == "resource_limit"
    assert killed.failure_phase == "training"
    assert killed.last_successful_epoch == 78
    assert killed.recoverability.can_safe_retry is True
    assert killed.recoverability.can_evaluate_best is False
    assert "OOM" not in killed.technical_message
    assert any("137" in evidence for evidence in killed.evidence)
    assert not any("confirmed cgroup OOM" in evidence for evidence in killed.evidence)


def test_marks_sigkill_as_confirmed_oom_only_with_event_delta() -> None:
    killed = _classify(
        exit_code=-9,
        resource_snapshot={"cgroup_oom_kill_delta": 1, "cgroup_memory_peak_bytes": 8 * 1024**3},
    )

    assert killed.code == "resource_limit"
    assert any("confirmed cgroup OOM" in evidence for evidence in killed.evidence)


def test_classifies_post_training_failure_with_recoverable_best_weight() -> None:
    diagnostic = _classify(
        message="RuntimeError: ONNX export failed",
        log_tail=["training completed", "RuntimeError: ONNX export failed"],
        failure_phase="export",
        last_successful_epoch=100,
        best_weight_path="training-runs/run-1/ultralytics/weights/best.pt",
        preserved_artifact_count=9,
    )

    assert diagnostic.failure_scope == "post_training"
    assert diagnostic.recoverability.can_evaluate_best is True


def test_classifies_strong_failure_signatures() -> None:
    cases = [
        ("disk_full", "OSError: [Errno 28] No space left on device"),
        ("device_unavailable", "ValueError: Invalid CUDA device cuda:0"),
        ("base_model_unavailable", "FileNotFoundError: yolo26s.pt not found"),
        ("dataset_invalid", "FileNotFoundError: Dataset images not found"),
        ("dependency_import", "ModuleNotFoundError: No module named 'ultralytics'"),
    ]

    for expected, message in cases:
        assert _classify(message=message, log_tail=[message]).code == expected


def test_classifies_opencv_allocation_failure_as_system_memory_limit() -> None:
    message = (
        "cv2.error: OpenCV(4.11.0) alloc.cpp:73: error: "
        "(-4:Insufficient memory) Failed to allocate 1216512 bytes "
        "in function 'cv::OutOfMemoryError'"
    )

    diagnostic = _classify(message=message, log_tail=[message])

    assert diagnostic.code == "resource_limit"
    assert "系统内存" in diagnostic.summary
    assert "图像尺寸" in diagnostic.action
    assert "DataLoader" in diagnostic.action


def test_import_error_requires_a_real_import_exception_signature() -> None:
    assert _classify(message="ImportError: cannot import name 'YOLO'").code == "dependency_import"
    assert _classify(message="cv::OutOfMemoryError").code == "resource_limit"


def test_unknown_failure_uses_runner_failed_fallback() -> None:
    assert _classify(message="unexpected worker failure").code == "runner_failed"


def test_known_exit_code_has_priority_over_vague_log_keyword() -> None:
    diagnostic = _classify(exit_code=137, log_tail=["old warning: no space left on device"])

    assert diagnostic.code == "resource_limit"
