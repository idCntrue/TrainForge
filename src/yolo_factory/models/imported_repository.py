from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import ImportedModelRecord, InferenceRunRecord


class ReferencedImportedModelDeletion(ValueError):
    pass


@dataclass(frozen=True)
class ImportedModel:
    id: str
    name: str
    task_type: str
    artifact_format: str
    original_name: str
    artifact_path: str
    size_bytes: int
    sha256: str
    status: str
    class_names: tuple[str, ...]
    created_at: datetime
    updated_at: datetime


class ImportedModelRepository:
    def __init__(self, registry: Registry) -> None:
        self._registry = registry

    def create(
        self, *, model_id: str, name: str, task_type: str, artifact_format: str,
        original_name: str, artifact_path: str, size_bytes: int, sha256: str,
        class_names: tuple[str, ...],
    ) -> ImportedModel:
        with session_scope(self._registry) as session:
            session.add(ImportedModelRecord(
                id=model_id, name=name, task_type=task_type, format=artifact_format,
                original_name=original_name, artifact_path=artifact_path,
                size_bytes=size_bytes, sha256=sha256, status="ready",
                class_names_json=json.dumps(list(class_names), ensure_ascii=False),
            ))
        return self.get_required(model_id)

    def get(self, model_id: str) -> ImportedModel | None:
        with session_scope(self._registry) as session:
            record = session.get(ImportedModelRecord, model_id)
            return _to_domain(record) if record else None

    def get_required(self, model_id: str) -> ImportedModel:
        model = self.get(model_id)
        if model is None:
            raise KeyError(model_id)
        return model

    def list(self) -> list[ImportedModel]:
        with session_scope(self._registry) as session:
            return [_to_domain(record) for record in session.scalars(
                select(ImportedModelRecord).order_by(ImportedModelRecord.created_at.desc())
            )]

    def delete(self, model_id: str) -> ImportedModel:
        with session_scope(self._registry) as session:
            record = session.get(ImportedModelRecord, model_id)
            if record is None:
                raise KeyError(model_id)
            inference_id = session.execute(
                select(InferenceRunRecord.id)
                .where(InferenceRunRecord.imported_model_id == model_id).limit(1)
            ).scalar_one_or_none()
            if inference_id is not None:
                raise ReferencedImportedModelDeletion(
                    f"imported model is referenced by inference run {inference_id}"
                )
            model = _to_domain(record)
            session.delete(record)
            return model


def _to_domain(record: ImportedModelRecord) -> ImportedModel:
    return ImportedModel(
        id=record.id, name=record.name, task_type=record.task_type,
        artifact_format=record.format, original_name=record.original_name,
        artifact_path=record.artifact_path, size_bytes=record.size_bytes,
        sha256=record.sha256, status=record.status,
        class_names=tuple(json.loads(record.class_names_json)),
        created_at=record.created_at, updated_at=record.updated_at,
    )
