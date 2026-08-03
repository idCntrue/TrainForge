from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yolo_factory.registry.database import Registry
from yolo_factory.training.resource_snapshot import read_training_memory_snapshot


def _process_memory() -> int | None:
    if os.name == "nt":
        return None
    try:
        import resource

        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except (ImportError, OSError, ValueError):
        return None


def _gpu_probe() -> dict[str, Any]:
    completed = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
        check=True,
        capture_output=True,
        text=True,
        timeout=2,
    )
    name, total, used, utilization = next(line for line in completed.stdout.splitlines() if line.strip()).split(", ")
    return {
        "name": name,
        "memory_total_bytes": int(float(total) * 1024 * 1024),
        "memory_used_bytes": int(float(used) * 1024 * 1024),
        "utilization_percent": float(utilization),
    }


class OperationalHealthCollector:
    def __init__(
        self,
        *,
        storage_root: Path,
        registry: Registry,
        active_work: Callable[[], dict[str, Any]],
        process_memory: Callable[[], int | None] = _process_memory,
        disk_usage: Callable[[str | Path], shutil._ntuple_diskusage] = shutil.disk_usage,
        memory_snapshot: Callable[[], dict[str, int | None]] = read_training_memory_snapshot,
        gpu_probe: Callable[[], dict[str, Any]] = _gpu_probe,
    ) -> None:
        self._storage_root = storage_root
        self._registry = registry
        self._active_work = active_work
        self._process_memory = process_memory
        self._disk_usage = disk_usage
        self._memory_snapshot = memory_snapshot
        self._gpu_probe = gpu_probe

    def collect(self) -> dict[str, Any]:
        warnings: list[str] = []
        usage = self._disk_usage(self._storage_root)
        database = self._storage_root / "registry" / "factory.db"
        try:
            with self._registry.engine.connect() as connection:
                quick_check = str(connection.exec_driver_sql("PRAGMA quick_check(1)").scalar_one())
        except Exception as error:
            quick_check = "unavailable"
            warnings.append(f"SQLite check unavailable: {error}")
        try:
            gpu = self._gpu_probe()
        except Exception as error:
            gpu = None
            warnings.append(f"GPU metrics unavailable: {error}")
        return {
            "sampled_at": datetime.now(timezone.utc).isoformat(),
            "api_process_rss_bytes": self._process_memory(),
            "memory": self._memory_snapshot(),
            "storage": {
                "total_bytes": int(usage.total),
                "used_bytes": int(usage.used),
                "free_bytes": int(usage.free),
                "free_percent": round((usage.free / usage.total * 100) if usage.total else 0.0, 2),
            },
            "gpu": gpu,
            "sqlite": {
                "quick_check": quick_check,
                "database_bytes": database.stat().st_size if database.is_file() else 0,
                "wal_bytes": database.with_name(f"{database.name}-wal").stat().st_size if database.with_name(f"{database.name}-wal").is_file() else 0,
            },
            "active_work": self._active_work(),
            "warnings": warnings,
        }
