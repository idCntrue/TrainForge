import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from yolo_factory.common.json_lines import read_json_lines
from yolo_factory.inference.repository import InferenceRunRepository


class InferenceExecutionError(RuntimeError):
    pass


class LocalInferenceExecutor:
    def __init__(self, repository: InferenceRunRepository, storage_root: Path, *, python_executable: str | None = None) -> None:
        self._repository = repository
        self._storage_root = storage_root
        self._python = python_executable or sys.executable
        self._processes: dict[str, subprocess.Popen] = {}

    def start(self, run_id: str, payload: dict) -> dict:
        run = self._repository.get_required(run_id)
        if run["status"] != "queued":
            raise InferenceExecutionError(f"cannot start inference from {run['status']}")
        directory = self._storage_root / "inference-runs" / run_id
        directory.mkdir(parents=True, exist_ok=False)
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps({"run_id": run_id, **payload}, ensure_ascii=False, indent=2), encoding="utf-8")
        log_stream = (directory / "runner.log").open("ab")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        process = subprocess.Popen(
            [self._python, "-m", "yolo_factory.inference.runner", "--manifest", str(manifest)],
            stdout=log_stream,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        log_stream.close()
        self._processes[run_id] = process
        (directory / "process.json").write_text(json.dumps({"pid": process.pid, "python": self._python}, sort_keys=True), encoding="utf-8")
        return self._repository.update(run_id, "running", progress=2, message="Inference runner started", pid=process.pid, run_directory=str(directory))

    def refresh(self, run_id: str) -> dict:
        run = self._repository.get_required(run_id)
        if run["status"] not in {"queued", "running"}:
            return run
        run_directory = Path(run["run_directory"]) if run.get("run_directory") else None
        if run_directory is not None:
            progress_path = run_directory / "progress.jsonl"
            if progress_path.is_file():
                events = read_json_lines(progress_path)
                if events:
                    event = events[-1]
                    status = event.get("status", "running")
                    result_path = run_directory / "result.json"
                    output_directory = run_directory if status == "completed" else None
                    return self._repository.update(
                        run_id,
                        status,
                        progress=float(event.get("progress", run["progress"])),
                        message=event.get("message", run["message"]),
                        output_directory=str(output_directory) if output_directory else None,
                        result_path=str(result_path) if status == "completed" and result_path.is_file() else None,
                    )
        process = self._processes.get(run_id)
        if process is not None and process.poll() not in {None, 0}:
            return self._repository.update(run_id, "failed", progress=100, message=f"Inference runner exited with code {process.returncode}")
        return run

    def cancel(self, run_id: str) -> dict:
        run = self._repository.get_required(run_id)
        if run["status"] not in {"queued", "running"}:
            return run
        process = self._processes.get(run_id)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        elif run.get("pid") and _process_exists(run["pid"]):
            os.kill(run["pid"], signal.SIGTERM)
            deadline = time.monotonic() + 3
            while _process_exists(run["pid"]) and time.monotonic() < deadline:
                time.sleep(0.02)
        return self._repository.update(run_id, "cancelled", progress=run["progress"], message="Cancellation requested")

    def recover_stale_runs(self) -> list[dict]:
        recovered = []
        for run in self._repository.list():
            if run["status"] not in {"queued", "running"}:
                continue
            current = self.refresh(run["id"])
            if current["status"] in {"queued", "running"} and (not current.get("pid") or not _process_exists(current["pid"])):
                recovered.append(self._repository.update(current["id"], "interrupted", progress=current["progress"], message="Runner process is no longer available"))
        return recovered


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True
