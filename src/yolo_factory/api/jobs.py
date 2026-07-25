from __future__ import annotations

import json
import threading
import traceback
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from pydantic import BaseModel
from sqlalchemy import delete, select

from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import BackgroundJobRecord


class JobStatus(BaseModel):
    id: str
    status: str
    progress: float
    message: str
    payload: Any = None


class JobTracker:
    def __init__(self, registry: Registry | None = None) -> None:
        self._registry = registry
        self._jobs: dict[str, JobStatus] = {}
        self._lock = threading.Lock()

    def create_job(self, message: str = "任务排队中") -> str:
        job_id = str(uuid.uuid4())
        if self._registry is None:
            with self._lock:
                self._jobs[job_id] = JobStatus(id=job_id, status="pending", progress=0.0, message=message)
            return job_id
        with session_scope(self._registry) as session:
            session.add(BackgroundJobRecord(
                id=job_id,
                status="pending",
                progress=0.0,
                message=message,
                heartbeat_at=datetime.now(timezone.utc),
            ))
        return job_id

    def update_job(
        self,
        job_id: str,
        status: str | None = None,
        progress: float | None = None,
        message: str | None = None,
        payload: Any = None,
    ) -> None:
        if self._registry is None:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                if status is not None:
                    job.status = status
                if progress is not None:
                    job.progress = progress
                if message is not None:
                    job.message = message
                if payload is not None:
                    job.payload = payload
            return
        now = datetime.now(timezone.utc)
        with session_scope(self._registry) as session:
            record = session.get(BackgroundJobRecord, job_id)
            if record is None:
                return
            if status is not None:
                record.status = status
            if progress is not None:
                record.progress = progress
            if message is not None:
                record.message = message
            if payload is not None:
                record.payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            record.heartbeat_at = now
            if record.status in {"completed", "failed", "cancelled", "interrupted"}:
                record.finished_at = now
                record.expires_at = now + timedelta(days=30 if record.status == "failed" else 7)

    def get_job(self, job_id: str) -> JobStatus | None:
        if self._registry is None:
            with self._lock:
                return self._jobs.get(job_id)
        with session_scope(self._registry) as session:
            record = session.get(BackgroundJobRecord, job_id)
            return _to_status(record) if record is not None else None

    def list_jobs(
        self,
        *,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JobStatus]:
        if self._registry is None:
            with self._lock:
                jobs = list(reversed(self._jobs.values()))
            if status is not None:
                jobs = [job for job in jobs if job.status == status]
            return jobs[offset:None if limit is None else offset + limit]
        statement = select(BackgroundJobRecord)
        if status is not None:
            statement = statement.where(BackgroundJobRecord.status == status)
        statement = statement.order_by(
            BackgroundJobRecord.created_at.desc(),
            BackgroundJobRecord.id.desc(),
        )
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        with session_scope(self._registry) as session:
            return [_to_status(record) for record in session.scalars(statement)]

    def recover_interrupted(self) -> list[str]:
        if self._registry is None:
            return []
        recovered: list[str] = []
        now = datetime.now(timezone.utc)
        with session_scope(self._registry) as session:
            records = session.scalars(
                select(BackgroundJobRecord).where(BackgroundJobRecord.status.in_(("pending", "running")))
            )
            for record in records:
                recovered.append(record.id)
                record.status = "interrupted"
                record.message = "API restarted before the background job completed"
                record.finished_at = now
                record.expires_at = now + timedelta(days=30)
        return recovered

    def purge_expired(self, *, limit: int = 200) -> int:
        if self._registry is None:
            return 0
        now = datetime.now(timezone.utc)
        with session_scope(self._registry) as session:
            ids = list(session.scalars(
                select(BackgroundJobRecord.id)
                .where(BackgroundJobRecord.expires_at.is_not(None), BackgroundJobRecord.expires_at < now)
                .limit(limit)
            ))
            if ids:
                session.execute(delete(BackgroundJobRecord).where(BackgroundJobRecord.id.in_(ids)))
        return len(ids)

    def start_background_task(
        self,
        target: Callable[[str, Any], None],
        args: Any = None,
        message: str = "正在执行后台任务",
    ) -> str:
        job_id = self.create_job(message)

        def wrapper() -> None:
            try:
                self.update_job(job_id, status="running", progress=0.0, message=message)
                target(job_id, args)
                current = self.get_job(job_id)
                if current is not None and current.status == "running":
                    self.update_job(job_id, status="completed", progress=100.0, message="任务已完成")
            except Exception as exc:
                traceback.print_exc()
                self.update_job(job_id, status="failed", message=f"任务执行失败: {exc}")

        threading.Thread(target=wrapper, name=f"job-{job_id}", daemon=True).start()
        return job_id


def _to_status(record: BackgroundJobRecord) -> JobStatus:
    return JobStatus(
        id=record.id,
        status=record.status,
        progress=record.progress,
        message=record.message,
        payload=json.loads(record.payload_json) if record.payload_json else None,
    )


job_tracker = JobTracker()
