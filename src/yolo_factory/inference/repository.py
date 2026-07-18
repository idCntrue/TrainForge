import json
from datetime import datetime, timezone

from sqlalchemy import select

from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import InferenceRunRecord


class ActiveInferenceRunDeletion(ValueError):
    pass


class InferenceRunRepository:
    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def create(self, *, run_id: str, model_version_id: str, mode: str, runtime: str, sources: list[str], confidence: float) -> dict:
        with session_scope(self._registry) as session:
            session.add(InferenceRunRecord(id=run_id, model_version_id=model_version_id, mode=mode, runtime=runtime, config_json=json.dumps({"sources": sources, "confidence": confidence}, sort_keys=True), status="queued", progress=0, message="Queued"))
        return self.get_required(run_id)

    def get_required(self, run_id: str) -> dict:
        with session_scope(self._registry) as session:
            record = session.get(InferenceRunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            return _to_dict(record)

    def list(self) -> list[dict]:
        with session_scope(self._registry) as session:
            return [_to_dict(record) for record in session.scalars(select(InferenceRunRecord).order_by(InferenceRunRecord.created_at.desc()))]

    def update(self, run_id: str, status: str, *, progress: float, message: str, output_directory: str | None = None, result_path: str | None = None, pid: int | None = None, run_directory: str | None = None) -> dict:
        with session_scope(self._registry) as session:
            record = session.get(InferenceRunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            record.status = status
            record.progress = progress
            record.message = message
            if pid is not None or run_directory is not None:
                config = json.loads(record.config_json)
                if pid is not None:
                    config["pid"] = pid
                if run_directory is not None:
                    config["run_directory"] = run_directory
                record.config_json = json.dumps(config, sort_keys=True)
            if output_directory:
                record.output_directory = output_directory
            if result_path:
                record.result_path = result_path
            if status in {"completed", "failed", "cancelled", "interrupted"}:
                record.finished_at = datetime.now(timezone.utc)
        return self.get_required(run_id)

    def delete(self, run_id: str) -> dict:
        with session_scope(self._registry) as session:
            record = session.get(InferenceRunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            if record.status in {"queued", "running"}:
                raise ActiveInferenceRunDeletion("active inference runs cannot be deleted")
            run = _to_dict(record)
            session.delete(record)
            return run


def _to_dict(record: InferenceRunRecord) -> dict:
    config = json.loads(record.config_json)
    return {"id": record.id, "model_version_id": record.model_version_id, "mode": record.mode, "runtime": record.runtime, "sources": config["sources"], "confidence": config["confidence"], "status": record.status, "progress": record.progress, "message": record.message, "pid": config.get("pid"), "run_directory": config.get("run_directory"), "output_directory": record.output_directory, "result_path": record.result_path, "created_at": record.created_at, "updated_at": record.updated_at, "finished_at": record.finished_at}
