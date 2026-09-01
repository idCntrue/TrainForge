"""Runtime environment and health telemetry for the system status page.

The health endpoint doubles as a lightweight liveness probe, so expensive
imports (``torch``, ``ultralytics``) and GPU discovery run exactly once per
process and are cached. Only cheap, real-time facts (disk usage, database size,
active job counts) are recomputed on each call.
"""

from __future__ import annotations

import functools
import platform as _platform
import shutil
from pathlib import Path

from sqlalchemy import func, select

from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import InferenceRunRecord, TrainingRunRecord

_ACTIVE_TRAINING_STATUSES = {"queued", "running", "evaluating", "exporting", "verifying"}
_ACTIVE_INFERENCE_STATUSES = {"queued", "running"}


@functools.lru_cache(maxsize=1)
def _probe_environment() -> dict:
    """Probe GPU and package versions once per process.

    ``import torch`` / ``import ultralytics`` are deliberately deferred into
    this cached function so the health endpoint stays fast after the first call.
    Any probe failure degrades gracefully to ``None`` values instead of taking
    the whole endpoint down.
    """
    versions = {"python": _platform.python_version(), "torch": None, "ultralytics": None, "cuda": None}
    gpu = {"available": False, "device": None, "memory_bytes": None, "cuda_version": None}
    try:
        import torch

        versions["torch"] = torch.__version__
        versions["cuda"] = torch.version.cuda
        if torch.cuda.is_available():
            gpu["available"] = True
            gpu["cuda_version"] = torch.version.cuda
            try:
                gpu["device"] = torch.cuda.get_device_name(0)
                gpu["memory_bytes"] = torch.cuda.get_device_properties(0).total_memory
            except Exception:
                pass
    except Exception:
        pass
    try:
        import ultralytics

        versions["ultralytics"] = ultralytics.__version__
    except Exception:
        pass
    return {"versions": versions, "gpu": gpu}


def _active_counts(registry: Registry) -> dict:
    with session_scope(registry) as session:
        training = session.scalar(
            select(func.count())
            .select_from(TrainingRunRecord)
            .where(TrainingRunRecord.status.in_(_ACTIVE_TRAINING_STATUSES))
        ) or 0
        inference = session.scalar(
            select(func.count())
            .select_from(InferenceRunRecord)
            .where(InferenceRunRecord.status.in_(_ACTIVE_INFERENCE_STATUSES))
        ) or 0
    return {"training": int(training), "inference": int(inference)}


def system_status(registry: Registry, root: Path, database_path: Path) -> dict:
    """Assemble the full system status payload for ``GET /api/health``."""
    environment = _probe_environment()
    disk = shutil.disk_usage(root)
    database_size = database_path.stat().st_size if database_path.is_file() else 0
    return {
        "status": "ok",
        "storage_root": str(root),
        "disk": {"total": disk.total, "used": disk.used, "free": disk.free},
        "gpu": environment["gpu"],
        "versions": environment["versions"],
        "active_jobs": _active_counts(registry),
        "database": {"path": str(database_path), "size_bytes": database_size},
    }
