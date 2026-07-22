from types import SimpleNamespace

from yolo_factory.training.resource_cleanup import cleanup_training_resources
from yolo_factory.training.storage_cleanup import StorageCleanupResult


def test_combines_safe_storage_and_process_local_memory_cleanup(tmp_path) -> None:
    calls: list[str] = []

    result = cleanup_training_resources(
        tmp_path,
        storage_cleanup=lambda root: (
            calls.append(f"storage:{root}"),
            StorageCleanupResult(released_bytes=4096, deleted_files=2, deleted_directories=1),
        )[1],
        collect=lambda: calls.append("gc") or 17,
        cuda_cleanup=lambda: calls.append("cuda") or True,
        disk_usage=lambda root: SimpleNamespace(total=10000, used=4000, free=6000),
        memory_snapshot=lambda: {"windows_available_commit_bytes": 8 * 1024**3},
    )

    assert calls == [f"storage:{tmp_path}", "gc", "cuda"]
    assert result.model_dump() == {
        "released_bytes": 4096,
        "deleted_files": 2,
        "deleted_directories": 1,
        "skipped_symlinks": 0,
        "python_collected_objects": 17,
        "cuda_cache_cleared": True,
        "disk_free_bytes": 6000,
        "disk_total_bytes": 10000,
        "resource_snapshot": {"windows_available_commit_bytes": 8 * 1024**3},
        "warnings": [],
    }


def test_optional_cuda_failure_is_a_non_fatal_warning(tmp_path) -> None:
    def unavailable_cuda() -> bool:
        raise RuntimeError("CUDA runtime unavailable")

    result = cleanup_training_resources(
        tmp_path,
        storage_cleanup=lambda root: StorageCleanupResult(errors=("locked.tmp",)),
        collect=lambda: 0,
        cuda_cleanup=unavailable_cuda,
        disk_usage=lambda root: SimpleNamespace(total=100, used=50, free=50),
        memory_snapshot=lambda: {},
    )

    assert result.cuda_cache_cleared is False
    assert result.warnings == ("locked.tmp", "CUDA cache cleanup skipped: CUDA runtime unavailable")
