import json
import subprocess
import sys
import uuid
from pathlib import Path


class ModelGateError(RuntimeError):
    pass


class LocalModelGateExecutor:
    def __init__(self, storage_root: Path, *, python_executable: str | None = None) -> None:
        self._storage_root = storage_root
        self._python = python_executable or sys.executable

    def run(self, model_id: str, payload: dict) -> tuple[dict, Path]:
        attempt = self._storage_root / "model-versions" / model_id / "gate-runs" / uuid.uuid4().hex
        attempt.mkdir(parents=True)
        manifest = attempt / "manifest.json"
        manifest.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
        log_path = attempt / "runner.log"
        with log_path.open("wb") as log:
            process = subprocess.run(
                [self._python, "-m", "yolo_factory.models.gate_runner", "--manifest", str(manifest)],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        result_path = attempt / "result.json"
        if not result_path.is_file():
            raise ModelGateError(f"model gate runner failed with exit code {process.returncode}; see {log_path}")
        return json.loads(result_path.read_text(encoding="utf-8")), result_path
