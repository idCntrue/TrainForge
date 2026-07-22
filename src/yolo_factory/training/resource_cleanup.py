from __future__ import annotations

import gc
import shutil
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from yolo_factory.training.resource_snapshot import read_training_memory_snapshot
from yolo_factory.training.storage_cleanup import StorageCleanupResult, cleanup_training_storage


@dataclass(frozen=True)
class TrainingResourceCleanupResult:
    released_bytes: int
    deleted_files: int
    deleted_directories: int
    skipped_symlinks: int
    python_collected_objects: int
    cuda_cache_cleared: bool
    disk_free_bytes: int
    disk_total_bytes: int
    resource_snapshot: dict[str, int | None]
    warnings: tuple[str, ...] = ()

    def model_dump(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["warnings"] = list(self.warnings)
        return payload


def _cleanup_loaded_cuda_cache() -> bool:
    torch = sys.modules.get("torch")
    if torch is None:
        return False
    cuda = getattr(torch, "cuda", None)
    if cuda is None or not cuda.is_available():
        return False
    cuda.empty_cache()
    return True


def cleanup_training_resources(
    storage_root: str | Path,
    *,
    storage_cleanup: Callable[[str | Path], StorageCleanupResult] = cleanup_training_storage,
    collect: Callable[[], int] = gc.collect,
    cuda_cleanup: Callable[[], bool] = _cleanup_loaded_cuda_cache,
    disk_usage: Callable[[str | Path], Any] = shutil.disk_usage,
    memory_snapshot: Callable[[], dict[str, int | None]] = read_training_memory_snapshot,
) -> TrainingResourceCleanupResult:
    root = Path(storage_root)
    storage = storage_cleanup(root)
    collected = collect()
    warnings = list(storage.errors)
    try:
        cuda_cache_cleared = cuda_cleanup()
    except Exception as exc:
        cuda_cache_cleared = False
        warnings.append(f"CUDA cache cleanup skipped: {exc}")
    usage = disk_usage(root)
    return TrainingResourceCleanupResult(
        released_bytes=storage.released_bytes,
        deleted_files=storage.deleted_files,
        deleted_directories=storage.deleted_directories,
        skipped_symlinks=storage.skipped_symlinks,
        python_collected_objects=collected,
        cuda_cache_cleared=cuda_cache_cleared,
        disk_free_bytes=usage.free,
        disk_total_bytes=usage.total,
        resource_snapshot=memory_snapshot(),
        warnings=tuple(warnings),
    )
