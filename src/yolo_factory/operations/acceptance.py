from __future__ import annotations

import argparse
import ctypes
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from yolo_factory.api.jobs import JobTracker
from yolo_factory.common.operation_guard import HeavyOperationGuard
from yolo_factory.inference.repository import InferenceRunRepository
from yolo_factory.operations.database_backup import DatabaseBackupService
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, ImportedModelRecord, Task
from yolo_factory.training.models import TrainingRunSpec
from yolo_factory.training.repository import TrainingRunRepository


class UnsafeAcceptanceRoot(RuntimeError):
    pass


@dataclass(frozen=True)
class AcceptanceResult:
    passed: bool
    json_path: Path
    markdown_path: Path


def _validate_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    configured = os.environ.get("YOLO_FACTORY_STORAGE_ROOT")
    if configured and resolved == Path(configured).expanduser().resolve():
        raise UnsafeAcceptanceRoot("acceptance root must not be the configured production storage root")
    if resolved.exists() and any(resolved.iterdir()):
        raise UnsafeAcceptanceRoot("acceptance root must be empty")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _seed_registry(registry) -> None:
    with session_scope(registry) as session:
        session.add(Task(
            id="acceptance-task",
            task_type="detect",
            annotation_format="yolo-detect",
            classes_json='["object"]',
        ))
    with session_scope(registry) as session:
        session.add(AnnotationExport(
            id="acceptance-export",
            task_id="acceptance-task",
            provider_project="acceptance",
            provider_version="1",
            zip_path="fixtures/annotations.zip",
            sha256="a" * 64,
        ))
    with session_scope(registry) as session:
        session.add(DatasetRelease(
            id="acceptance-release",
            task_id="acceptance-task",
            annotation_export_id="acceptance-export",
            version="0.0.0",
            release_path="fixtures/release",
            status="published",
        ))
    with session_scope(registry) as session:
        session.add(ImportedModelRecord(
            id="acceptance-model",
            name="acceptance",
            task_type="detect",
            format="onnx",
            original_name="acceptance.onnx",
            artifact_path="fixtures/acceptance.onnx",
            size_bytes=1,
            sha256="b" * 64,
            status="ready",
            class_names_json='["object"]',
        ))


def _current_rss_bytes() -> int:
    if os.name != "nt":
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value if sys_platform_is_macos() else value * 1024)

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    psapi.GetProcessMemoryInfo.restype = ctypes.c_int
    process = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        raise OSError("GetProcessMemoryInfo failed")
    return int(counters.WorkingSetSize)


def sys_platform_is_macos() -> bool:
    import sys

    return sys.platform == "darwin"


def _registry_round_trip(registry) -> None:
    with session_scope(registry) as session:
        if session.get(Task, "acceptance-task") is None:
            raise AssertionError("registry round trip failed")


def _background_job_recovery(registry) -> None:
    tracker = JobTracker(registry)
    job_id = tracker.create_job("acceptance recovery")
    tracker.update_job(job_id, status="running")
    if tracker.recover_interrupted() != [job_id]:
        raise AssertionError("background job was not recovered")
    if tracker.get_job(job_id).status != "interrupted":
        raise AssertionError("background job recovery status is invalid")


def _heavy_lease_reclaim(registry) -> None:
    abandoned = HeavyOperationGuard(registry, lease_seconds=0.01)
    abandoned._acquire_lease("abandoned")
    time.sleep(0.02)
    replacement = HeavyOperationGuard(registry, lease_seconds=1)
    with replacement.acquire("replacement"):
        if replacement.active_operation != "replacement":
            raise AssertionError("expired heavy-operation lease was not reclaimed")


def _simulated_training_lifecycle(registry) -> None:
    repository = TrainingRunRepository(registry)
    repository.create(
        TrainingRunSpec("acceptance", "detect", "acceptance-release", "yolo11n.pt", 1, 1, 320, "cpu"),
        run_id="acceptance-training",
    )
    for status in ("running", "evaluating", "exporting", "verifying", "completed"):
        repository.transition("acceptance-training", status)
    if repository.get_required("acceptance-training").status != "completed":
        raise AssertionError("simulated training did not complete")


def _simulated_inference_lifecycle(registry) -> None:
    repository = InferenceRunRepository(registry)
    repository.create(
        run_id="acceptance-inference",
        mode="image",
        runtime="onnx",
        sources=["fixtures/image.jpg"],
        confidence=0.25,
        imported_model_id="acceptance-model",
    )
    repository.update("acceptance-inference", "running", progress=50, message="Running")
    result = repository.update("acceptance-inference", "completed", progress=100, message="Completed")
    if result["status"] != "completed":
        raise AssertionError("simulated inference did not complete")


def _database_backup(registry, database: Path, root: Path) -> None:
    backup = DatabaseBackupService(
        registry,
        database,
        database.parent / "backups",
        retention=2,
    ).create()
    if backup.integrity_check != "ok" or not backup.path.is_file():
        raise AssertionError("verified database backup was not created")
    if not backup.path.is_relative_to(root):
        raise AssertionError("database backup escaped acceptance root")


def _write_reports(root: Path, payload: dict) -> tuple[Path, Path]:
    json_path = root / "acceptance-report.json"
    markdown_path = root / "acceptance-report.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# TrainForge Stability Acceptance",
        "",
        f"- Result: {'PASSED' if payload['passed'] else 'FAILED'}",
        f"- Samples: {payload['samples']}",
        f"- Started: {payload['started_at']}",
        f"- Finished: {payload['finished_at']}",
        "",
        "## Checks",
        "",
    ]
    lines.extend(f"- {name}: {status}" for name, status in payload["checks"].items())
    if payload["errors"]:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {name}: {message}" for name, message in payload["errors"].items())
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def run_acceptance(
    root: Path,
    *,
    duration_seconds: float,
    sample_interval_seconds: float,
    max_growth_bytes: int = 256 * 1024 * 1024,
) -> AcceptanceResult:
    if duration_seconds <= 0 or sample_interval_seconds <= 0:
        raise ValueError("acceptance duration and sample interval must be positive")
    root = _validate_root(root)
    started = datetime.now(timezone.utc)
    database = root / "registry" / "factory.db"
    registry = create_registry(database)
    checks: dict[str, str] = {}
    errors: dict[str, str] = {}

    actions: list[tuple[str, Callable[[], None]]] = [
        ("registry_round_trip", lambda: (_seed_registry(registry), _registry_round_trip(registry))),
        ("background_job_recovery", lambda: _background_job_recovery(registry)),
        ("heavy_lease_reclaim", lambda: _heavy_lease_reclaim(registry)),
        ("simulated_training_lifecycle", lambda: _simulated_training_lifecycle(registry)),
        ("simulated_inference_lifecycle", lambda: _simulated_inference_lifecycle(registry)),
        ("database_backup", lambda: _database_backup(registry, database, root)),
    ]
    for name, action in actions:
        try:
            action()
            checks[name] = "passed"
        except Exception as error:
            checks[name] = "failed"
            errors[name] = str(error)

    samples: list[int] = []
    deadline = time.monotonic() + duration_seconds
    while True:
        samples.append(_current_rss_bytes())
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(sample_interval_seconds, remaining))
    growth = max(samples) - samples[0]
    checks["resource_growth"] = "passed" if growth <= max_growth_bytes else "failed"
    if checks["resource_growth"] == "failed":
        errors["resource_growth"] = f"RSS grew by {growth} bytes; limit is {max_growth_bytes}"

    finished = datetime.now(timezone.utc)
    passed = all(status == "passed" for status in checks.values())
    payload = {
        "passed": passed,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": duration_seconds,
        "samples": len(samples),
        "rss_start_bytes": samples[0],
        "rss_peak_bytes": max(samples),
        "rss_growth_bytes": growth,
        "checks": checks,
        "errors": errors,
    }
    json_path, markdown_path = _write_reports(root, payload)
    registry.engine.dispose()
    return AcceptanceResult(passed=passed, json_path=json_path, markdown_path=markdown_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run isolated TrainForge stability acceptance")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--duration-seconds", type=float, default=60)
    parser.add_argument("--sample-interval-seconds", type=float, default=1)
    parser.add_argument("--max-growth-bytes", type=int, default=256 * 1024 * 1024)
    args = parser.parse_args()
    result = run_acceptance(
        args.root,
        duration_seconds=args.duration_seconds,
        sample_interval_seconds=args.sample_interval_seconds,
        max_growth_bytes=args.max_growth_bytes,
    )
    print(f"JSON report: {result.json_path}")
    print(f"Markdown report: {result.markdown_path}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
