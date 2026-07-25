import json
import subprocess
import sys
import uuid
import threading
from pathlib import Path


class ModelGateError(RuntimeError):
    pass


class LocalModelGateExecutor:
    def __init__(self, storage_root: Path, *, python_executable: str | None = None, timeout_seconds: float = 1200) -> None:
        self._storage_root = storage_root
        self._python = python_executable or sys.executable
        self._timeout_seconds = timeout_seconds
        self._processes: dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()

    def run(self, model_id: str, payload: dict) -> tuple[dict, Path]:
        attempt = self._storage_root / "model-versions" / model_id / "gate-runs" / uuid.uuid4().hex
        attempt.mkdir(parents=True)
        manifest = attempt / "manifest.json"
        manifest.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        log_path = attempt / "runner.log"
        with log_path.open("wb") as log:
            process = subprocess.Popen(
                [self._python, "-m", "yolo_factory.models.gate_runner", "--manifest", str(manifest)],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            with self._lock:
                self._processes[model_id] = process
            try:
                process.wait(timeout=self._timeout_seconds)
            except subprocess.TimeoutExpired as exc:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                raise ModelGateError(
                    f"model gate runner timed out after {self._timeout_seconds:g} seconds; see {log_path}"
                ) from exc
            finally:
                with self._lock:
                    self._processes.pop(model_id, None)
        result_path = attempt / "result.json"
        if not result_path.is_file():
            raise ModelGateError(f"model gate runner failed with exit code {process.returncode}; see {log_path}")
        return json.loads(result_path.read_text(encoding="utf-8")), result_path

    def cancel(self, model_id: str) -> bool:
        with self._lock:
            process = self._processes.get(model_id)
        if process is None or process.poll() is not None:
            return False
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        return True
