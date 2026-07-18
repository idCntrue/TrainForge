import json
import os
import traceback
import uuid
from pathlib import Path
from threading import Lock
from typing import Callable

from yolo_factory.annotations.sam_runner import predict_with_model


class SamExecutionError(RuntimeError):
    pass


class LocalSamExecutor:
    def __init__(self, storage_root: Path, *, python_executable: str | None = None, model_factory: Callable | None = None, predictor: Callable | None = None) -> None:
        self._storage_root = storage_root
        self._model_factory = model_factory or self._create_model
        self._predictor = predictor or predict_with_model
        self._models: dict[str, object] = {}
        self._model_locks: dict[str, Lock] = {}
        self._pool_lock = Lock()

    @staticmethod
    def _create_model(model_path: str):
        from ultralytics import SAM

        return SAM(model_path)

    def _model(self, model_path: str) -> tuple[object, Lock, bool]:
        configured_model_dir = os.environ.get("YOLO_FACTORY_MODEL_DIR")
        path = Path(model_path)
        if configured_model_dir and not path.is_absolute() and path.parent == Path("."):
            candidate = (Path(configured_model_dir) / path.name).resolve()
            if candidate.is_file():
                model_path = str(candidate)
        with self._pool_lock:
            model = self._models.get(model_path)
            loaded = model is None
            if model is None:
                model = self._model_factory(model_path)
                self._models[model_path] = model
                self._model_locks[model_path] = Lock()
            return model, self._model_locks[model_path], loaded

    def run(self, frame_id: str, payload: dict) -> tuple[dict, Path]:
        directory = self._storage_root / "sam-runs" / frame_id / uuid.uuid4().hex
        directory.mkdir(parents=True)
        manifest = directory / "manifest.json"
        manifest.write_text(json.dumps({"frame_id": frame_id, **payload}, ensure_ascii=False, indent=2), encoding="utf-8")
        log_path = directory / "runner.log"
        try:
            model, inference_lock, model_was_loaded = self._model(payload["model"])
            with inference_lock:
                result = self._predictor(model, payload)
            result = {**result, "model_was_loaded": model_was_loaded}
            (directory / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            return result, directory
        except Exception as exc:
            log_path.write_text(traceback.format_exc(), encoding="utf-8")
            raise SamExecutionError(f"SAM inference failed; see {log_path}") from exc
