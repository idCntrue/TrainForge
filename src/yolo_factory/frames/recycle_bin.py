from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

from sqlalchemy import delete, func, select

from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import (
    AnnotationImageRecord, AnnotationShapeRecord, FrameAsset, VideoAsset,
)
from yolo_factory.storage.objects import LocalObjectStorage, ObjectStorage


@dataclass(frozen=True)
class PurgeResult:
    deleted_count: int
    released_bytes: int
    failed_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecycleSummary:
    item_count: int
    total_bytes: int
    earliest_purge_after: datetime | None


class FrameRecycleBin:
    def __init__(self, registry: Registry, storage: ObjectStorage, *, retention_days: int = 7, operations_root: Path | None = None) -> None:
        self.registry = registry
        self.storage = storage
        self.retention = timedelta(days=retention_days)
        self.operations_root = operations_root
        if operations_root is not None:
            operations_root.mkdir(parents=True, exist_ok=True)

    def _operation_path(self, action: str, request_id: str) -> Path | None:
        if self.operations_root is None:
            return None
        digest = hashlib.sha256(f"{action}\0{request_id}".encode()).hexdigest()
        return self.operations_root / f"{digest}.json"

    def _load_operation(self, action: str, request_id: str | None) -> dict | None:
        if not request_id:
            return None
        path = self._operation_path(action, request_id)
        if path is None or not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _store_operation(self, action: str, request_id: str | None, result: dict) -> None:
        if not request_id:
            return
        path = self._operation_path(action, request_id)
        if path is None:
            return
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)

    def trash(self, frame_ids: list[str], *, now: datetime | None = None, request_id: str | None = None) -> int:
        cached = self._load_operation("trash", request_id)
        if cached is not None:
            return int(cached["affected_count"])
        if not frame_ids:
            return 0
        timestamp = now or datetime.now(timezone.utc)
        with session_scope(self.registry) as session:
            frames = list(session.scalars(select(FrameAsset).where(FrameAsset.id.in_(frame_ids))))
            if len(frames) != len(set(frame_ids)):
                raise KeyError("frame not found")
            changed = 0
            for frame in frames:
                if frame.lifecycle_status == "trashed":
                    continue
                frame.pre_trash_status = frame.status
                frame.lifecycle_status = "trashed"
                frame.trashed_at = timestamp
                frame.purge_after = timestamp + self.retention
                changed += 1
        self._store_operation("trash", request_id, {"affected_count": changed})
        return changed

    def restore(self, frame_ids: list[str], *, request_id: str | None = None) -> int:
        cached = self._load_operation("restore", request_id)
        if cached is not None:
            return int(cached["affected_count"])
        if not frame_ids:
            return 0
        with session_scope(self.registry) as session:
            frames = list(session.scalars(select(FrameAsset).where(FrameAsset.id.in_(frame_ids))))
            if len(frames) != len(set(frame_ids)):
                raise KeyError("frame not found")
            changed = 0
            for frame in frames:
                if frame.lifecycle_status != "trashed":
                    continue
                frame.status = frame.pre_trash_status or "candidate"
                frame.lifecycle_status = "active"
                frame.pre_trash_status = None
                frame.trashed_at = None
                frame.purge_after = None
                changed += 1
        self._store_operation("restore", request_id, {"affected_count": changed})
        return changed

    def purge(self, frame_ids: list[str], *, request_id: str | None = None) -> PurgeResult:
        cached = self._load_operation("purge", request_id)
        if cached is not None:
            return PurgeResult(int(cached["deleted_count"]), int(cached["released_bytes"]), tuple(cached.get("failed_keys", [])))
        if not frame_ids:
            return PurgeResult(0, 0)
        keys: list[str] = []
        released = 0
        with session_scope(self.registry) as session:
            frames = list(session.scalars(select(FrameAsset).where(FrameAsset.id.in_(frame_ids))))
            if len(frames) != len(set(frame_ids)):
                raise KeyError("frame not found")
            if any(frame.lifecycle_status != "trashed" for frame in frames):
                raise ValueError("permanent delete is limited to the recycle bin")
            for frame in frames:
                keys.append(frame.storage_key or frame.stored_path)
                released += frame.size_bytes
                session.execute(delete(AnnotationShapeRecord).where(AnnotationShapeRecord.frame_id == frame.id))
                session.execute(delete(AnnotationImageRecord).where(AnnotationImageRecord.frame_id == frame.id))
                video_id = frame.video_id
                session.delete(frame)
                session.flush()
                remaining = session.scalar(
                    select(func.count()).select_from(FrameAsset).where(FrameAsset.video_id == video_id)
                ) or 0
                if remaining == 0:
                    source = session.get(VideoAsset, video_id)
                    if source is not None:
                        session.delete(source)
        failed: list[str] = []
        for key in keys:
            try:
                self.storage.delete(key)
            except ValueError:
                if not isinstance(self.storage, LocalObjectStorage):
                    failed.append(key)
                    continue
                try:
                    legacy_key = Path(key).resolve().relative_to(self.storage.root).as_posix()
                    self.storage.delete(legacy_key)
                except (OSError, ValueError):
                    failed.append(key)
            except OSError:
                failed.append(key)
        result = PurgeResult(len(frame_ids), released, tuple(failed))
        self._store_operation("purge", request_id, {
            "deleted_count": result.deleted_count,
            "released_bytes": result.released_bytes,
            "failed_keys": list(result.failed_keys),
        })
        return result

    def purge_expired(self, *, now: datetime | None = None, limit: int = 100) -> PurgeResult:
        timestamp = now or datetime.now(timezone.utc)
        with session_scope(self.registry) as session:
            frame_ids = list(session.scalars(
                select(FrameAsset.id)
                .where(
                    FrameAsset.lifecycle_status == "trashed",
                    FrameAsset.purge_after.is_not(None),
                    FrameAsset.purge_after <= timestamp,
                )
                .order_by(FrameAsset.purge_after, FrameAsset.id)
                .limit(limit)
            ))
        return self.purge(frame_ids)

    def summary(self) -> RecycleSummary:
        with session_scope(self.registry) as session:
            count, total, earliest = session.execute(
                select(func.count(), func.coalesce(func.sum(FrameAsset.size_bytes), 0), func.min(FrameAsset.purge_after))
                .where(FrameAsset.lifecycle_status == "trashed")
            ).one()
        return RecycleSummary(int(count), int(total), earliest)
