from __future__ import annotations

from threading import Lock
from typing import Callable

from yolo_factory.labeling.predictions import extract_detections


class DetectorExecutionError(RuntimeError):
    pass


class LocalDetectorExecutor:
    """Warm, single-model detector cache for interactive annotation suggestions.

    At most one model is kept in memory: the target server has 800 MB of RAM,
    so switching models evicts the previous one instead of growing.
    """

    def __init__(self, *, model_factory: Callable[[str, str], object] | None = None) -> None:
        self._model_factory = model_factory or self._create_model
        self._model_path: str | None = None
        self._task_type: str | None = None
        self._model: object | None = None
        self._lock = Lock()

    @staticmethod
    def _create_model(model_path: str, task_type: str):
        from ultralytics import YOLO

        return YOLO(model_path, task=task_type)

    def _get_model(self, model_path: str, task_type: str):
        if self._model is not None and self._model_path == model_path and self._task_type == task_type:
            return self._model
        self._model = None
        self._model_path = None
        self._task_type = None
        self._model = self._model_factory(model_path, task_type)
        self._model_path = model_path
        self._task_type = task_type
        return self._model

    def loaded_model_path(self) -> str | None:
        return self._model_path

    def unload(self) -> None:
        """Drop the warm model so a subprocess can use the same memory budget."""
        with self._lock:
            self._model = None
            self._model_path = None
            self._task_type = None

    def detect(self, image_path: str, model_path: str, task_type: str, *, confidence: float = 0.25, iou: float = 0.7, imgsz: int = 640) -> dict:
        with self._lock:
            try:
                model = self._get_model(model_path, task_type)
                results = model.predict(image_path, imgsz=imgsz, conf=confidence, iou=iou, verbose=False)
                result = results[0]
                names = result.names
                if not isinstance(names, dict):
                    names = {index: str(name) for index, name in enumerate(names)}
                return {
                    "detections": extract_detections(result, task_type),
                    "names": {int(key): str(value) for key, value in names.items()},
                    "speed": getattr(result, "speed", {}) or {},
                }
            except Exception as exc:
                raise DetectorExecutionError(f"model inference failed: {exc}") from exc
