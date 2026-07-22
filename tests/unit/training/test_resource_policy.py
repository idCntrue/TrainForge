from types import SimpleNamespace

import pytest

from yolo_factory.training.resource_policy import (
    InsufficientTrainingMemory,
    InsufficientTrainingStorage,
    TrainingResourcePolicy,
    UnsafeTrainingConfiguration,
)


GIB = 1024**3


def test_loads_safe_defaults_from_empty_environment() -> None:
    policy = TrainingResourcePolicy.from_environment({})

    assert policy.cpu_threads == 4
    assert policy.detect_max_batch == 4
    assert policy.segment_max_batch == 1
    assert policy.max_image_size == 640
    assert policy.min_free_disk_gb == 8
    assert policy.min_free_disk_percent == 10
    assert policy.min_available_commit_gb == 8
    assert policy.runtime_min_available_commit_gb == 4
    assert policy.min_available_memory_gb == 4


def test_loads_overrides_and_rejects_invalid_environment() -> None:
    policy = TrainingResourcePolicy.from_environment({
        "CPU_TRAINING_THREADS": "2",
        "CPU_DETECT_MAX_BATCH": "3",
        "CPU_SEGMENT_MAX_BATCH": "1",
        "CPU_TRAINING_MAX_IMAGE_SIZE": "512",
        "TRAINING_MIN_FREE_DISK_GB": "8",
        "TRAINING_MIN_FREE_DISK_PERCENT": "15",
        "TRAINING_MIN_AVAILABLE_COMMIT_GB": "12",
        "TRAINING_RUNTIME_MIN_AVAILABLE_COMMIT_GB": "5",
        "TRAINING_MIN_AVAILABLE_MEMORY_GB": "6",
    })

    assert policy.cpu_threads == 2
    assert policy.detect_max_batch == 3
    assert policy.segment_max_batch == 1
    assert policy.max_image_size == 512
    assert policy.min_free_disk_gb == 8
    assert policy.min_free_disk_percent == 15
    assert policy.min_available_commit_gb == 12
    assert policy.runtime_min_available_commit_gb == 5
    assert policy.min_available_memory_gb == 6

    with pytest.raises(ValueError, match="CPU_TRAINING_THREADS"):
        TrainingResourcePolicy.from_environment({"CPU_TRAINING_THREADS": "zero"})
    with pytest.raises(ValueError, match="CPU_SEGMENT_MAX_BATCH"):
        TrainingResourcePolicy.from_environment({"CPU_SEGMENT_MAX_BATCH": "0"})
    with pytest.raises(ValueError, match="TRAINING_MIN_FREE_DISK_PERCENT"):
        TrainingResourcePolicy.from_environment({"TRAINING_MIN_FREE_DISK_PERCENT": "101"})
    with pytest.raises(ValueError, match="TRAINING_MIN_AVAILABLE_COMMIT_GB"):
        TrainingResourcePolicy.from_environment({"TRAINING_MIN_AVAILABLE_COMMIT_GB": "zero"})
    with pytest.raises(ValueError, match="TRAINING_RUNTIME_MIN_AVAILABLE_COMMIT_GB"):
        TrainingResourcePolicy.from_environment({"TRAINING_RUNTIME_MIN_AVAILABLE_COMMIT_GB": "0"})
    with pytest.raises(ValueError, match="must not exceed"):
        TrainingResourcePolicy.from_environment({"TRAINING_RUNTIME_MIN_AVAILABLE_COMMIT_GB": "9"})


def test_rejects_unsafe_cpu_parameters_and_accepts_bounded_gpu_parameters() -> None:
    policy = TrainingResourcePolicy.from_environment({})

    policy.validate_request("detect", "cpu", batch=4, image_size=640)
    policy.validate_request("segment", "cpu", batch=1, image_size=640)
    policy.validate_request("segment", "cuda:0", batch=2, image_size=1280)

    with pytest.raises(UnsafeTrainingConfiguration, match="CPU detection training batch must be at most 4"):
        policy.validate_request("detect", "cpu", batch=5, image_size=320)
    with pytest.raises(UnsafeTrainingConfiguration, match="CPU segmentation training batch must be at most 1"):
        policy.validate_request("segment", "cpu", batch=2, image_size=320)
    with pytest.raises(UnsafeTrainingConfiguration, match="CPU training image size must be at most 640"):
        policy.validate_request("segment", "cpu", batch=1, image_size=672)


def test_rejects_gpu_parameters_above_configured_limits() -> None:
    policy = TrainingResourcePolicy.from_environment({
        "GPU_DETECT_MAX_BATCH": "4",
        "GPU_SEGMENT_MAX_BATCH": "1",
        "GPU_TRAINING_MAX_IMAGE_SIZE": "640",
        "GPU_ALLOWED_DEVICES": "cuda:0",
    })

    policy.validate_request("detect", "cuda:0", batch=4, image_size=640)

    with pytest.raises(UnsafeTrainingConfiguration, match="GPU detection training batch must be at most 4"):
        policy.validate_request("detect", "cuda:0", batch=5, image_size=640)
    with pytest.raises(UnsafeTrainingConfiguration, match="GPU training image size must be at most 640"):
        policy.validate_request("segment", "cuda:0", batch=1, image_size=672)
    with pytest.raises(UnsafeTrainingConfiguration, match="not permitted"):
        policy.validate_request("detect", "cuda:1", batch=1, image_size=320)


def test_builds_bounded_execution_policy() -> None:
    policy = TrainingResourcePolicy.from_environment({"CPU_TRAINING_THREADS": "3"})

    cpu = policy.execution_policy("cpu")
    gpu = policy.execution_policy("cuda:0")

    assert cpu.model_dump() == {"workers": 0, "cache": False, "cpu_threads": 3}
    assert gpu.model_dump() == {"workers": 0, "cache": False, "cpu_threads": None}


def test_rejects_disk_when_either_absolute_or_percentage_reserve_is_too_low(tmp_path) -> None:
    policy = TrainingResourcePolicy.from_environment({})

    with pytest.raises(InsufficientTrainingStorage, match="at least 8 GiB and 10%") as absolute:
        policy.validate_free_disk(
            tmp_path,
            usage=lambda _: SimpleNamespace(total=50 * GIB, used=43 * GIB, free=7 * GIB),
        )
    assert absolute.value.failed_checks == ("absolute",)
    assert absolute.value.free_gib == pytest.approx(7.0)
    assert absolute.value.free_percent == pytest.approx(14.0)

    with pytest.raises(InsufficientTrainingStorage, match="at least 8 GiB and 10%") as percentage:
        policy.validate_free_disk(
            tmp_path,
            usage=lambda _: SimpleNamespace(total=1000 * GIB, used=980 * GIB, free=20 * GIB),
        )
    assert percentage.value.failed_checks == ("percentage",)
    assert percentage.value.free_gib == pytest.approx(20.0)
    assert percentage.value.free_percent == pytest.approx(2.0)

    policy.validate_free_disk(
        tmp_path,
        usage=lambda _: SimpleNamespace(total=100 * GIB, used=80 * GIB, free=20 * GIB),
    )


def test_disk_error_preserves_two_decimal_places() -> None:
    policy = TrainingResourcePolicy(min_free_disk_gb=10)

    with pytest.raises(InsufficientTrainingStorage) as error:
        policy.validate_free_disk(
            ".",
            usage=lambda _: SimpleNamespace(total=40 * GIB, used=30.04 * GIB, free=9.96 * GIB),
        )

    assert "9.96 GiB" in str(error.value)
    assert error.value.as_detail()["free_gib"] == 9.96


def test_rejects_low_windows_commit_memory_with_process_evidence() -> None:
    policy = TrainingResourcePolicy.from_environment({})

    with pytest.raises(InsufficientTrainingMemory) as captured:
        policy.validate_memory_snapshot({
            "windows_available_commit_bytes": 3 * GIB,
            "windows_available_physical_bytes": 5 * GIB,
            "windows_leaspac_process_count": 30,
            "windows_leaspac_private_bytes": 31 * GIB,
        })

    detail = captured.value.as_detail()
    assert detail["code"] == "insufficient_training_memory"
    assert detail["failed_checks"] == ["commit"]
    assert detail["leaspac_process_count"] == 30
    assert detail["leaspac_private_gib"] == 31.0
    assert "LeASPac.exe 30 个" in detail["message"]


def test_rejects_low_windows_physical_memory_and_accepts_linux_snapshot() -> None:
    policy = TrainingResourcePolicy.from_environment({})

    with pytest.raises(InsufficientTrainingMemory) as captured:
        policy.validate_memory_snapshot({
            "windows_available_commit_bytes": 20 * GIB,
            "windows_available_physical_bytes": 2 * GIB,
            "windows_leaspac_process_count": 0,
            "windows_leaspac_private_bytes": 0,
        })
    assert captured.value.failed_checks == ("physical",)

    policy.validate_memory_snapshot({"cgroup_memory_current_bytes": 2 * GIB})
    policy.validate_memory_snapshot({
        "windows_available_commit_bytes": None,
        "windows_available_physical_bytes": None,
    })


def test_runtime_memory_gate_allows_expected_physical_usage_when_commit_is_safe() -> None:
    policy = TrainingResourcePolicy()

    with pytest.raises(InsufficientTrainingMemory):
        policy.validate_memory_snapshot({
            "windows_available_commit_bytes": int(7.96 * GIB),
            "windows_available_physical_bytes": 8 * GIB,
        })

    policy.validate_runtime_memory_snapshot({
        "windows_available_commit_bytes": 12 * GIB,
        "windows_available_physical_bytes": int(3.49 * GIB),
    })

    policy.validate_runtime_memory_snapshot({
        "windows_available_commit_bytes": int(7.96 * GIB),
        "windows_available_physical_bytes": int(2.15 * GIB),
    })


def test_runtime_memory_gate_still_rejects_low_commit_memory() -> None:
    policy = TrainingResourcePolicy()

    with pytest.raises(InsufficientTrainingMemory) as error:
        policy.validate_runtime_memory_snapshot({
            "windows_available_commit_bytes": int(3.99 * GIB),
            "windows_available_physical_bytes": 6 * GIB,
        })

    assert error.value.failed_checks == ("commit",)
    assert error.value.required_commit_gib == 4
