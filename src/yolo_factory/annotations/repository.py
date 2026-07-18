from __future__ import annotations

import json
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select

from yolo_factory.annotations.domain import AnnotationImage, AnnotationShape
from yolo_factory.annotations.geometry import validate_geometry
from yolo_factory.common.task_metadata import decode_task_classes
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import AnnotationImageRecord, AnnotationShapeRecord, FrameAsset, FrameBatch, Task, VideoCollection
from yolo_factory.storage.objects import ObjectStorage


class AnnotationConflict(ValueError):
    pass


class InvalidAnnotationTransition(ValueError):
    pass


class AnnotationSourceUnavailable(ValueError):
    pass


class AnnotationRepository:
    def __init__(self, registry: Registry, object_storage: ObjectStorage | None = None) -> None:
        self._registry = registry
        self._object_storage = object_storage

    def sync_selected_frames(self, task_id: str) -> list[AnnotationImage]:
        self._sync_selected_frames(task_id)
        return self.list(task_id=task_id)

    def sync_selected_frame_counts(self, task_id: str) -> tuple[int, int]:
        synced_count = self._sync_selected_frames(task_id)
        with session_scope(self._registry) as session:
            total_count = session.scalar(
                select(func.count()).select_from(AnnotationImageRecord).where(AnnotationImageRecord.task_id == task_id)
            ) or 0
        return synced_count, total_count

    def _sync_selected_frames(self, task_id: str) -> int:
        synced_count = 0
        with session_scope(self._registry) as session:
            task = session.get(Task, task_id)
            if task is None:
                raise KeyError(task_id)
            statement = (select(FrameAsset).join(FrameBatch, FrameAsset.batch_id == FrameBatch.id).join(VideoCollection, FrameBatch.collection_id == VideoCollection.id).where(VideoCollection.task_id == task_id, FrameAsset.status == "selected", FrameAsset.lifecycle_status == "active").order_by(FrameAsset.id))
            for frame in session.scalars(statement):
                if session.get(AnnotationImageRecord, frame.id) is None:
                    source_path = self._resolve_frame_path(frame)
                    try:
                        with Image.open(source_path) as image:
                            width, height = image.size
                    except (FileNotFoundError, UnidentifiedImageError, OSError) as exc:
                        raise AnnotationSourceUnavailable(
                            f"annotation source image is unavailable: {frame.stored_path}"
                        ) from exc
                    session.add(AnnotationImageRecord(frame_id=frame.id, task_id=task_id, image_path=str(source_path), width=width, height=height, status="pending", revision=0))
                    synced_count += 1
        return synced_count

    def _resolve_frame_path(self, frame: FrameAsset) -> Path:
        stored_path = Path(frame.stored_path)
        if stored_path.is_absolute():
            return stored_path.resolve()
        storage_key = frame.storage_key or frame.stored_path
        if self._object_storage is None:
            raise AnnotationSourceUnavailable(
                f"relative annotation source has no storage resolver: {frame.stored_path}"
            )
        try:
            return self._object_storage.open_path(storage_key)
        except (OSError, ValueError) as exc:
            raise AnnotationSourceUnavailable(
                f"annotation source image is unavailable: {frame.stored_path}"
            ) from exc

    def list(self, *, task_id: str | None = None, status: str | None = None) -> list[AnnotationImage]:
        statement = select(AnnotationImageRecord).join(FrameAsset, FrameAsset.id == AnnotationImageRecord.frame_id).where(FrameAsset.lifecycle_status == "active").order_by(AnnotationImageRecord.created_at, AnnotationImageRecord.frame_id)
        if task_id:
            statement = statement.where(AnnotationImageRecord.task_id == task_id)
        if status:
            statement = statement.where(AnnotationImageRecord.status == status)
        with session_scope(self._registry) as session:
            return [self._to_domain(session, record) for record in session.scalars(statement)]

    def list_page(
        self,
        *,
        task_id: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[dict], int, dict[str, int]]:
        filters = [FrameAsset.lifecycle_status == "active"]
        if task_id:
            filters.append(AnnotationImageRecord.task_id == task_id)
        if status:
            filters.append(AnnotationImageRecord.status == status)

        summary_statement = (
            select(
                AnnotationImageRecord.frame_id,
                AnnotationImageRecord.task_id,
                Task.task_type,
                AnnotationImageRecord.status,
                AnnotationImageRecord.revision,
                func.count(AnnotationShapeRecord.id).label("shape_count"),
                AnnotationImageRecord.created_at,
                AnnotationImageRecord.updated_at,
            )
            .join(Task, Task.id == AnnotationImageRecord.task_id)
            .join(FrameAsset, FrameAsset.id == AnnotationImageRecord.frame_id)
            .outerjoin(AnnotationShapeRecord, AnnotationShapeRecord.frame_id == AnnotationImageRecord.frame_id)
            .where(*filters)
            .group_by(
                AnnotationImageRecord.frame_id,
                AnnotationImageRecord.task_id,
                Task.task_type,
                AnnotationImageRecord.status,
                AnnotationImageRecord.revision,
                AnnotationImageRecord.created_at,
                AnnotationImageRecord.updated_at,
            )
            .order_by(AnnotationImageRecord.created_at, AnnotationImageRecord.frame_id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        count_statement = select(func.count()).select_from(AnnotationImageRecord).join(FrameAsset, FrameAsset.id == AnnotationImageRecord.frame_id).where(*filters)
        status_count_statement = select(AnnotationImageRecord.status, func.count()).join(FrameAsset, FrameAsset.id == AnnotationImageRecord.frame_id).where(FrameAsset.lifecycle_status == "active").group_by(AnnotationImageRecord.status)
        if task_id:
            status_count_statement = status_count_statement.where(AnnotationImageRecord.task_id == task_id)

        with session_scope(self._registry) as session:
            items = [dict(row._mapping) for row in session.execute(summary_statement)]
            total = session.scalar(count_statement) or 0
            status_counts = {"pending": 0, "annotated": 0, "reviewed": 0}
            status_counts.update({row.status: row[1] for row in session.execute(status_count_statement)})
        return items, total, status_counts

    def get_required(self, frame_id: str) -> AnnotationImage:
        with session_scope(self._registry) as session:
            record = session.get(AnnotationImageRecord, frame_id)
            frame = session.get(FrameAsset, frame_id)
            if record is None or frame is None or frame.lifecycle_status != "active":
                raise KeyError(frame_id)
            return self._to_domain(session, record)

    def create_shape(self, frame_id: str, *, revision: int, class_id: int, class_name: str, shape_type: str, coordinates: list[float], source: str) -> tuple[AnnotationShape, AnnotationImage]:
        with session_scope(self._registry) as session:
            image = self._mutable_image(session, frame_id, revision)
            task = session.get(Task, image.task_id)
            classes, _ = decode_task_classes(task.classes_json)
            if class_id < 0 or class_id >= len(classes) or classes[class_id] != class_name:
                raise ValueError("shape class does not match task contract")
            if (task.task_type == "detect" and shape_type != "box") or (task.task_type == "segment" and shape_type != "polygon"):
                raise ValueError("shape type does not match task type")
            shape = AnnotationShapeRecord(id=f"shape-{uuid.uuid4().hex}", frame_id=frame_id, class_id=class_id, class_name=class_name, shape_type=shape_type, coordinates_json=json.dumps(validate_geometry(shape_type, coordinates)), source=source)
            session.add(shape)
            image.revision += 1
            image.status = "annotated"
            session.flush()
            shape_id = shape.id
        current = self.get_required(frame_id)
        return next(shape for shape in current.shapes if shape.id == shape_id), current

    def update_shape(self, frame_id: str, shape_id: str, *, revision: int, class_id: int, class_name: str, coordinates: list[float]) -> AnnotationImage:
        with session_scope(self._registry) as session:
            image = self._mutable_image(session, frame_id, revision)
            shape = session.get(AnnotationShapeRecord, shape_id)
            if shape is None or shape.frame_id != frame_id:
                raise KeyError(shape_id)
            task = session.get(Task, image.task_id)
            classes, _ = decode_task_classes(task.classes_json)
            if class_id < 0 or class_id >= len(classes) or classes[class_id] != class_name:
                raise ValueError("shape class does not match task contract")
            shape.class_id = class_id
            shape.class_name = class_name
            shape.coordinates_json = json.dumps(validate_geometry(shape.shape_type, coordinates))
            image.revision += 1
        return self.get_required(frame_id)

    def delete_shape(self, frame_id: str, shape_id: str, *, revision: int) -> AnnotationImage:
        with session_scope(self._registry) as session:
            image = self._mutable_image(session, frame_id, revision)
            shape = session.get(AnnotationShapeRecord, shape_id)
            if shape is None or shape.frame_id != frame_id:
                raise KeyError(shape_id)
            session.delete(shape)
            session.flush()
            remaining = session.scalar(select(AnnotationShapeRecord.id).where(AnnotationShapeRecord.frame_id == frame_id).limit(1))
            image.revision += 1
            image.status = "annotated" if remaining else "pending"
        return self.get_required(frame_id)

    def set_status(self, frame_id: str, *, revision: int, status: str) -> AnnotationImage:
        with session_scope(self._registry) as session:
            image = session.get(AnnotationImageRecord, frame_id)
            if image is None:
                raise KeyError(frame_id)
            self._check_revision(image, revision)
            if status not in {"pending", "annotated", "reviewed"}:
                raise InvalidAnnotationTransition("unknown annotation status")
            shape_exists = session.scalar(select(AnnotationShapeRecord.id).where(AnnotationShapeRecord.frame_id == frame_id).limit(1)) is not None
            if status in {"annotated", "reviewed"} and not shape_exists:
                raise InvalidAnnotationTransition("annotated and reviewed images require shapes")
            if image.status == "reviewed" and status != "annotated":
                raise InvalidAnnotationTransition("reviewed image can only return to annotated")
            image.status = status
            image.revision += 1
        return self.get_required(frame_id)

    def _mutable_image(self, session, frame_id: str, revision: int) -> AnnotationImageRecord:
        image = session.get(AnnotationImageRecord, frame_id)
        if image is None:
            raise KeyError(frame_id)
        self._check_revision(image, revision)
        if image.status == "reviewed":
            raise InvalidAnnotationTransition("reviewed image is read-only")
        return image

    @staticmethod
    def _check_revision(image: AnnotationImageRecord, revision: int) -> None:
        if image.revision != revision:
            raise AnnotationConflict(f"stale annotation revision: expected {image.revision}, got {revision}")

    @staticmethod
    def _to_domain(session, record: AnnotationImageRecord) -> AnnotationImage:
        task = session.get(Task, record.task_id)
        shapes = list(session.scalars(select(AnnotationShapeRecord).where(AnnotationShapeRecord.frame_id == record.frame_id).order_by(AnnotationShapeRecord.created_at, AnnotationShapeRecord.id)))
        classes, _ = decode_task_classes(task.classes_json)
        return AnnotationImage(frame_id=record.frame_id, task_id=record.task_id, task_type=task.task_type, image_path=record.image_path, width=record.width, height=record.height, status=record.status, revision=record.revision, classes=tuple(classes), shapes=tuple(AnnotationShape(id=shape.id, class_id=shape.class_id, class_name=shape.class_name, shape_type=shape.shape_type, coordinates=tuple(json.loads(shape.coordinates_json)), source=shape.source, created_at=shape.created_at, updated_at=shape.updated_at) for shape in shapes), created_at=record.created_at, updated_at=record.updated_at)
