from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select

from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import ModelVersionRecord, TrainingRunRecord
from yolo_factory.training.models import TrainingRun, TrainingRunSpec


class InvalidTrainingTransition(ValueError):
    pass


class ActiveTrainingRunDeletion(ValueError):
    pass


class ReferencedTrainingRunDeletion(ValueError):
    pass


_TRANSITIONS = {
    "queued": {"running", "cancelled"},
    "running": {"evaluating", "failed", "cancelled", "interrupted"},
    "evaluating": {"exporting", "failed", "interrupted"},
    "exporting": {"verifying", "failed", "interrupted"},
    "verifying": {"completed", "failed", "interrupted"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
    "interrupted": set(),
}


class TrainingRunRepository:
    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def create(self, spec: TrainingRunSpec, *, run_id: str) -> TrainingRun:
        record = TrainingRunRecord(
            id=run_id,
            name=spec.name,
            task_type=spec.task_type,
            dataset_release_id=spec.dataset_release_id,
            base_model=spec.base_model,
            config_json=json.dumps(
                {
                    "epochs": spec.epochs,
                    "batch": spec.batch,
                    "image_size": spec.image_size,
                    "device": spec.device,
                    "selected_classes": list(spec.selected_classes),
                    "class_aliases": spec.class_aliases,
                    "source_run_id": spec.source_run_id,
                    "execution_mode": spec.execution_mode,
                    "retry_strategy": spec.retry_strategy,
                    "request_id": spec.request_id,
                    "preset_id": spec.preset_id,
                    "patience": spec.patience,
                    "optimizer": spec.optimizer,
                    "close_mosaic": spec.close_mosaic,
                    "augment_profile": spec.augment_profile,
                    "augmentation": spec.augmentation,
                },
                sort_keys=True,
            ),
            status="queued",
            progress=0.0,
            phase="queued",
            message="Queued",
        )
        with session_scope(self._registry) as session:
            session.add(record)
        return self.get_required(run_id)

    def get(self, run_id: str) -> TrainingRun | None:
        with session_scope(self._registry) as session:
            record = session.get(TrainingRunRecord, run_id)
            return _to_domain(record) if record is not None else None

    def get_required(self, run_id: str) -> TrainingRun:
        run = self.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def list(self, *, status: str | None = None) -> list[TrainingRun]:
        statement = select(TrainingRunRecord)
        if status is not None:
            statement = statement.where(TrainingRunRecord.status == status)
        statement = statement.order_by(
            TrainingRunRecord.created_at.desc(),
            TrainingRunRecord.id.desc(),
        )
        with session_scope(self._registry) as session:
            return [_to_domain(record) for record in session.scalars(statement)]

    def find_retry(self, source_run_id: str, request_id: str) -> TrainingRun | None:
        return next((
            run for run in self.list()
            if run.spec.source_run_id == source_run_id and run.spec.request_id == request_id
        ), None)

    def related(self, run_id: str) -> list[TrainingRun]:
        return [run for run in self.list() if run.spec.source_run_id == run_id]

    def delete(self, run_id: str) -> TrainingRun:
        with session_scope(self._registry) as session:
            record = session.get(TrainingRunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            if record.status in {"queued", "running", "evaluating", "exporting", "verifying"}:
                raise ActiveTrainingRunDeletion("active training runs cannot be deleted")
            model_id = session.execute(
                select(ModelVersionRecord.id).where(ModelVersionRecord.training_run_id == run_id)
            ).scalar_one_or_none()
            if model_id is not None:
                raise ReferencedTrainingRunDeletion(f"training run is referenced by model {model_id}")
            run = _to_domain(record)
            session.delete(record)
            return run

    def update_runtime(
        self,
        run_id: str,
        *,
        progress: float | None = None,
        phase: str | None = None,
        message: str | None = None,
        heartbeat_at: datetime | None = None,
        epoch: int | None = None,
        total_epochs: int | None = None,
        metrics: dict | None = None,
        artifacts: dict | None = None,
    ) -> TrainingRun:
        with session_scope(self._registry) as session:
            record = session.get(TrainingRunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            if record.status in {"completed", "failed", "cancelled", "interrupted"}:
                return _to_domain(record)
            if progress is not None:
                record.progress = max(record.progress, progress)
            if phase is not None:
                record.phase = phase
            if message is not None:
                record.message = message
            if heartbeat_at is not None:
                record.heartbeat_at = heartbeat_at
            if epoch is not None or total_epochs is not None or metrics is not None or artifacts is not None:
                config = json.loads(record.config_json)
                runtime = config.setdefault("_runtime", {})
                if epoch is not None:
                    runtime["epoch"] = epoch
                if total_epochs is not None:
                    runtime["total_epochs"] = total_epochs
                if metrics is not None:
                    runtime["metrics"] = metrics
                if artifacts is not None:
                    runtime["artifacts"] = artifacts
                record.config_json = json.dumps(config, sort_keys=True)
        return self.get_required(run_id)

    def transition(
        self,
        run_id: str,
        status: str,
        *,
        progress: float | None = None,
        phase: str | None = None,
        message: str | None = None,
        pid: int | None = None,
        run_directory: str | None = None,
        heartbeat_at: datetime | None = None,
        exit_code: int | None = None,
        epoch: int | None = None,
        total_epochs: int | None = None,
        metrics: dict | None = None,
        artifacts: dict | None = None,
    ) -> TrainingRun:
        with session_scope(self._registry) as session:
            record = session.get(TrainingRunRecord, run_id)
            if record is None:
                raise KeyError(run_id)
            if status not in _TRANSITIONS.get(record.status, set()):
                raise InvalidTrainingTransition(f"{record.status} -> {status}")
            record.status = status
            record.progress = 100.0 if status == "completed" else (progress if progress is not None else record.progress)
            record.phase = phase or status
            record.message = message or record.message
            if pid is not None:
                record.pid = pid
            if run_directory is not None:
                record.run_directory = run_directory
            if heartbeat_at is not None:
                record.heartbeat_at = heartbeat_at
            if exit_code is not None:
                record.exit_code = exit_code
            if epoch is not None or total_epochs is not None or metrics is not None or artifacts is not None:
                config = json.loads(record.config_json)
                runtime = config.setdefault("_runtime", {})
                if epoch is not None:
                    runtime["epoch"] = epoch
                if total_epochs is not None:
                    runtime["total_epochs"] = total_epochs
                if metrics is not None:
                    runtime["metrics"] = metrics
                if artifacts is not None:
                    runtime["artifacts"] = artifacts
                record.config_json = json.dumps(config, sort_keys=True)
            if status == "cancelled":
                record.cancel_requested_at = datetime.now(timezone.utc)
            if status in {"completed", "failed", "cancelled", "interrupted"}:
                record.finished_at = datetime.now(timezone.utc)
        return self.get_required(run_id)


def _to_domain(record: TrainingRunRecord) -> TrainingRun:
    config = json.loads(record.config_json)
    runtime = config.get("_runtime", {})
    return TrainingRun(
        id=record.id,
        spec=TrainingRunSpec(
            name=record.name,
            task_type=record.task_type,
            dataset_release_id=record.dataset_release_id,
            base_model=record.base_model,
            epochs=config["epochs"],
            batch=config["batch"],
            image_size=config["image_size"],
            device=config["device"],
            selected_classes=tuple(config.get("selected_classes", [])),
            class_aliases=config.get("class_aliases", {}),
            source_run_id=config.get("source_run_id"),
            execution_mode=config.get("execution_mode", "train"),
            retry_strategy=config.get("retry_strategy"),
            request_id=config.get("request_id"),
            preset_id=config.get("preset_id", "custom"),
            patience=config.get("patience", 20),
            optimizer=config.get("optimizer", "auto"),
            close_mosaic=config.get("close_mosaic", 10),
            augment_profile=config.get("augment_profile", "standard"),
            augmentation=config.get("augmentation", {}),
        ),
        status=record.status,
        progress=record.progress,
        phase=record.phase,
        message=record.message,
        pid=record.pid,
        run_directory=record.run_directory,
        heartbeat_at=record.heartbeat_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
        finished_at=record.finished_at,
        exit_code=record.exit_code,
        cancel_requested_at=record.cancel_requested_at,
        epoch=runtime.get("epoch"),
        total_epochs=runtime.get("total_epochs"),
        metrics=runtime.get("metrics", {}),
        artifacts=runtime.get("artifacts", {}),
    )
