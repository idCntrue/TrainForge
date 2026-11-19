from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select

from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import AnnotationImageRecord, AnnotationShapeRecord, PrelabelRunRecord


@dataclass(frozen=True)
class PrelabelRun:
    id: str
    job_id: str | None
    batch_id: str | None
    task_id: str
    model_source: str
    model_name: str
    confidence: float
    iou: float
    status: str
    frames_total: int
    frames_processed: int
    frames_skipped: int
    shapes_created: int
    unmapped_classes: tuple[str, ...]
    error: str | None
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime


class PrelabelRunRepository:
    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def create(self, *, run_id: str, job_id: str, batch_id: str | None, task_id: str, model_source: str, model_name: str, confidence: float, iou: float, frames_total: int) -> PrelabelRun:
        with session_scope(self._registry) as session:
            session.add(PrelabelRunRecord(
                id=run_id, job_id=job_id, batch_id=batch_id, task_id=task_id,
                model_source=model_source, model_name=model_name,
                confidence=confidence, iou=iou, status="running",
                frames_total=frames_total, started_at=datetime.now(timezone.utc),
            ))
        return self.get_required(run_id)

    def update(self, run_id: str, **fields) -> None:
        with session_scope(self._registry) as session:
            record = session.get(PrelabelRunRecord, run_id)
            if record is None:
                return
            for key, value in fields.items():
                if key == "unmapped_classes":
                    record.unmapped_classes_json = json.dumps(list(value), ensure_ascii=False)
                    continue
                setattr(record, key, value)

    def get(self, run_id: str) -> PrelabelRun | None:
        with session_scope(self._registry) as session:
            record = session.get(PrelabelRunRecord, run_id)
            return _to_domain(record) if record is not None else None

    def get_required(self, run_id: str) -> PrelabelRun:
        run = self.get(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def list(self, *, task_id: str | None = None, limit: int = 20) -> list[PrelabelRun]:
        statement = select(PrelabelRunRecord).order_by(PrelabelRunRecord.created_at.desc()).limit(limit)
        if task_id:
            statement = statement.where(PrelabelRunRecord.task_id == task_id)
        with session_scope(self._registry) as session:
            return [_to_domain(record) for record in session.scalars(statement)]


def adoption_stats(registry: Registry, *, model_source: str | None = None, task_id: str | None = None) -> dict:
    shape_filters = [AnnotationShapeRecord.model_source.is_not(None)]
    if model_source:
        shape_filters.append(AnnotationShapeRecord.model_source == model_source)
    if task_id:
        shape_filters.append(
            AnnotationShapeRecord.frame_id.in_(
                select(AnnotationImageRecord.frame_id).where(AnnotationImageRecord.task_id == task_id)
            )
        )
    with session_scope(registry) as session:
        totals = {"created": 0, "draft": 0, "confirmed": 0, "rejected": 0}
        for status, count in session.execute(
            select(AnnotationShapeRecord.status, func.count())
            .where(*shape_filters)
            .group_by(AnnotationShapeRecord.status)
        ):
            totals["created"] += int(count)
            totals[status] = int(count)
        by_class = []
        for class_name, status, count in session.execute(
            select(AnnotationShapeRecord.class_name, AnnotationShapeRecord.status, func.count())
            .where(*shape_filters)
            .group_by(AnnotationShapeRecord.class_name, AnnotationShapeRecord.status)
        ):
            by_class.append({"class_name": class_name, "status": status, "count": int(count)})
    total = totals["created"]
    decided = totals["confirmed"] + totals["rejected"]
    return {
        "model_source": model_source,
        "totals": totals,
        "adoption_rate": round(totals["confirmed"] / decided, 4) if decided else None,
        "by_class": by_class,
    }


def _to_domain(record: PrelabelRunRecord) -> PrelabelRun:
    return PrelabelRun(
        id=record.id, job_id=record.job_id, batch_id=record.batch_id,
        task_id=record.task_id, model_source=record.model_source,
        model_name=record.model_name, confidence=record.confidence, iou=record.iou,
        status=record.status, frames_total=record.frames_total,
        frames_processed=record.frames_processed, frames_skipped=record.frames_skipped,
        shapes_created=record.shapes_created,
        unmapped_classes=tuple(json.loads(record.unmapped_classes_json or "[]")),
        error=record.error, started_at=record.started_at,
        finished_at=record.finished_at, created_at=record.created_at,
    )
