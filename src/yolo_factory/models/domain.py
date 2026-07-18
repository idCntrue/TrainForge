from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ModelVersionSpec:
    name: str
    version: str
    task_type: str
    training_run_id: str
    dataset_release_id: str
    selected_classes: tuple[str, ...]
    class_aliases: dict[str, str]
    pt_path: str
    metrics: dict[str, float | None]
    quality_report: dict | None = None


@dataclass(frozen=True)
class ModelVersion:
    id: str
    spec: ModelVersionSpec
    status: str
    gates: dict[str, bool]
    artifacts: dict[str, dict]
    environment: dict[str, str]
    gate_report_path: str | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    archived_at: datetime | None
