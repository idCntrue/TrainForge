import json
import os
import signal
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from yolo_factory.common.json_lines import read_json_lines
from yolo_factory.training.manifest import write_manifest
from yolo_factory.training.models import TrainingRun
from yolo_factory.training.repository import InvalidTrainingTransition, TrainingRunRepository
from yolo_factory.training.resource_policy import TrainingResourcePolicy
from yolo_factory.training.resource_snapshot import read_training_memory_snapshot
from yolo_factory.training.failure_diagnostics import classify_training_failure


class ActiveTrainingRunError(RuntimeError):
    pass


_ACTIVE_STATUSES = {"running", "evaluating", "exporting", "verifying"}


class LocalTrainingExecutor:
    def __init__(
        self,
        repository: TrainingRunRepository,
        storage_root: Path,
        *,
        python_executable: str | None = None,
        engine: str = "ultralytics",
        simulation_step_seconds: float = 0.15,
        resource_policy: TrainingResourcePolicy | None = None,
    ) -> None:
        self._repository = repository
        self._storage_root = storage_root
        self._python = python_executable or sys.executable
        self._engine = engine
        self._simulation_step_seconds = simulation_step_seconds
        self._resource_policy = resource_policy or TrainingResourcePolicy.from_environment(os.environ)
        self._processes: dict[str, subprocess.Popen] = {}

    def recover_stale_runs(self) -> list[TrainingRun]:
        recovered: list[TrainingRun] = []
        for run in self._repository.list():
            if run.status not in _ACTIVE_STATUSES:
                continue
            current = self.refresh(run.id)
            if current.status not in _ACTIVE_STATUSES:
                continue
            if current.pid is None or not _process_exists(current.pid):
                recovered.append(
                    self._repository.transition(
                        current.id,
                        "interrupted",
                        message="Runner process is no longer available",
                    )
                )
        return recovered

    def start(
        self,
        run_id: str,
        *,
        dataset_release_path: Path | None = None,
        data_yaml_path: Path | None = None,
    ) -> TrainingRun:
        active = [run for run in self._repository.list() if run.status in _ACTIVE_STATUSES and run.id != run_id]
        if active:
            raise ActiveTrainingRunError(active[0].id)
        run = self._repository.get_required(run_id)
        if run.status != "queued":
            raise InvalidTrainingTransition(f"{run.status} -> running")
        initial_resources = read_training_memory_snapshot()
        if self._engine == "ultralytics":
            self._resource_policy.validate_memory_snapshot(initial_resources)
        run_directory = self._storage_root / "training-runs" / run_id
        run_directory.mkdir(parents=True, exist_ok=False)
        execution = self._resource_policy.execution_policy(run.spec.device)
        manifest_path = write_manifest(
            run_directory / "manifest.json",
            run_id,
            run.spec,
            engine=self._engine,
            dataset_release_path=dataset_release_path,
            data_yaml_path=data_yaml_path,
            simulation_step_seconds=self._simulation_step_seconds,
            execution=execution,
        )
        log_stream = (run_directory / "runner.log").open("ab")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        process_environment = os.environ.copy()
        if execution.cpu_threads is not None:
            thread_count = str(execution.cpu_threads)
            process_environment.update({
                "OMP_NUM_THREADS": thread_count,
                "MKL_NUM_THREADS": thread_count,
                "OPENBLAS_NUM_THREADS": thread_count,
                "NUMEXPR_NUM_THREADS": thread_count,
            })
        process = subprocess.Popen(
            [self._python, "-m", "yolo_factory.training.runner", "--manifest", str(manifest_path)],
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
            env=process_environment,
        )
        log_stream.close()
        (run_directory / "process.json").write_text(
            json.dumps({"pid": process.pid, "python": self._python, "initial_resources": initial_resources}, sort_keys=True),
            encoding="utf-8",
        )
        self._processes[run_id] = process
        return self._repository.transition(
            run_id,
            "running",
            phase="training",
            message="Runner process started",
            pid=process.pid,
            run_directory=str(run_directory),
        )

    def refresh(self, run_id: str) -> TrainingRun:
        run = self._repository.get_required(run_id)
        if run.run_directory:
            progress_path = Path(run.run_directory) / "progress.jsonl"
            if progress_path.exists():
                for event in read_json_lines(progress_path):
                    current = self._repository.get_required(run_id)
                    if current.status in {"completed", "failed", "cancelled", "interrupted"}:
                        break
                    event_status = event["status"]
                    heartbeat = datetime.fromisoformat(event["timestamp"]) if event.get("timestamp") else None
                    if event_status == current.status:
                        self._repository.update_runtime(
                            run_id,
                            progress=float(event["progress"]),
                            phase=event["phase"],
                            message=event["message"],
                            heartbeat_at=heartbeat,
                            epoch=event.get("epoch"),
                            total_epochs=event.get("total_epochs"),
                            metrics=event.get("metrics"),
                            artifacts=event.get("artifacts"),
                        )
                    elif event_status in {"cancelled", "failed", "interrupted"} or event_status in {"evaluating", "exporting", "verifying", "completed"}:
                        try:
                            if event_status == "failed":
                                self._write_failure_diagnostic(
                                    current,
                                    exit_code=1,
                                    event=event,
                                )
                            self._repository.transition(
                                run_id,
                                event_status,
                                progress=float(event["progress"]),
                                phase=event["phase"],
                                message=event["message"],
                                heartbeat_at=heartbeat,
                                epoch=event.get("epoch"),
                                total_epochs=event.get("total_epochs"),
                                metrics=event.get("metrics"),
                                artifacts=event.get("artifacts"),
                            )
                        except InvalidTrainingTransition:
                            continue
        process = self._processes.get(run_id)
        current = self._repository.get_required(run_id)
        if process is not None and process.poll() not in {None, 0} and current.status not in {"completed", "failed", "cancelled", "interrupted"}:
            diagnostic = self._write_failure_diagnostic(
                current,
                exit_code=process.returncode,
            )
            current = self._repository.transition(
                run_id,
                "failed",
                message=diagnostic.summary,
                exit_code=process.returncode,
            )
        elif process is None and current.status in _ACTIVE_STATUSES and (
            current.pid is None or not _process_exists(current.pid)
        ):
            current = self._repository.transition(
                run_id,
                "interrupted",
                message="Runner process is no longer available",
            )
        return current

    def _write_failure_diagnostic(
        self,
        run: TrainingRun,
        *,
        exit_code: int | None,
        event: dict | None = None,
    ):
        event = event or {}
        if not run.run_directory:
            raise RuntimeError(f"training run {run.id} has no run directory for failure diagnostics")
        run_directory = Path(run.run_directory).resolve()
        events = read_json_lines(run_directory / "progress.jsonl")
        latest = event or (events[-1] if events else {})
        last_epoch = latest.get("last_successful_epoch", latest.get("epoch", run.epoch))
        total_epochs = latest.get("total_epochs", run.total_epochs or run.spec.epochs)
        phase = latest.get("phase") or run.phase or "unknown"
        log_path = run_directory / "runner.log"
        log_tail = (
            log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-200:]
            if log_path.is_file() else []
        )
        best_weight = run_directory / "ultralytics" / "weights" / "best.pt"
        best_weight_path = None
        if best_weight.is_file() and best_weight.stat().st_size > 0:
            resolved_weight = best_weight.resolve()
            try:
                resolved_weight.relative_to(run_directory)
                best_weight_path = resolved_weight.relative_to(self._storage_root.resolve()).as_posix()
            except ValueError:
                best_weight_path = None
        preserved = sum(1 for path in run_directory.rglob("*") if path.is_file() and not path.name.endswith(".tmp"))
        disk = shutil.disk_usage(run_directory)
        resource_snapshot = read_training_memory_snapshot()
        process_metadata = _read_json(run_directory / "process.json")
        initial_oom_kill = (process_metadata.get("initial_resources") or {}).get("cgroup_memory_oom_kill")
        current_oom_kill = resource_snapshot.get("cgroup_memory_oom_kill")
        resource_snapshot["cgroup_oom_kill_delta"] = (
            max(0, current_oom_kill - initial_oom_kill)
            if current_oom_kill is not None and initial_oom_kill is not None
            else None
        )
        resource_snapshot.update({
            "disk_free_bytes": disk.free,
            "configured_memory_limit_bytes": _parse_byte_size(os.environ.get("API_MEMORY_LIMIT")),
        })
        message = latest.get("technical_message") or latest.get("message") or ""
        diagnostic = classify_training_failure(
            exit_code=exit_code,
            message=message,
            log_tail=log_tail,
            failure_phase=phase,
            last_successful_epoch=last_epoch,
            total_epochs=total_epochs,
            best_weight_path=best_weight_path,
            preserved_artifact_count=preserved,
            exception_type=latest.get("exception_type"),
            traceback=latest.get("traceback"),
            occurred_at=latest.get("timestamp"),
            resource_snapshot=resource_snapshot,
        )
        _write_json_atomic(run_directory / "failure.json", diagnostic.model_dump())
        return diagnostic

    def cancel(self, run_id: str) -> TrainingRun:
        run = self._repository.get_required(run_id)
        process = self._processes.get(run_id)
        if process is not None and process.poll() is None:
            _terminate_process_tree(process.pid)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                _terminate_process_tree(process.pid, force=True)
                process.wait(timeout=3)
        elif run.pid is not None and _process_exists(run.pid):
            _terminate_process_tree(run.pid)
            deadline = time.monotonic() + 3
            while _process_exists(run.pid) and time.monotonic() < deadline:
                time.sleep(0.02)
            if _process_exists(run.pid):
                _terminate_process_tree(run.pid, force=True)
        if run.status == "queued":
            return self._repository.transition(run_id, "cancelled", message="Cancelled before start")
        return self._repository.transition(run_id, "cancelled", progress=run.progress, message="Cancellation requested")


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ValueError, SystemError):
        return False
    return True


def _terminate_process_tree(
    pid: int,
    *,
    force: bool = False,
    platform_name: str | None = None,
) -> None:
    platform_name = platform_name or os.name
    if platform_name == "nt":
        command = ["taskkill", "/PID", str(pid), "/T", "/F"]
        subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    os.killpg(pid, signal.SIGKILL if force else signal.SIGTERM)


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _parse_byte_size(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value.strip().lower()
    multipliers = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}
    suffix = normalized[-1]
    try:
        if suffix in multipliers:
            return int(float(normalized[:-1]) * multipliers[suffix])
        return int(normalized)
    except ValueError:
        return None
