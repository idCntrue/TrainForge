from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class TrainingRunSpec:
    name: str
    task_type: str
    dataset_release_id: str
    base_model: str
    epochs: int
    batch: int
    image_size: int
    device: str
    selected_classes: tuple[str, ...] = ()
    class_aliases: dict[str, str] = field(default_factory=dict)
    source_run_id: str | None = None
    execution_mode: str = "train"
    retry_strategy: str | None = None
    request_id: str | None = None
    preset_id: str = "custom"
    patience: int = 20
    optimizer: str = "auto"
    close_mosaic: int = 10
    augment_profile: str = "standard"
    augmentation: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingRun:
    id: str
    spec: TrainingRunSpec
    status: str
    progress: float
    phase: str
    message: str
    pid: int | None
    run_directory: str | None
    heartbeat_at: datetime | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    cancel_requested_at: datetime | None
    epoch: int | None = None
    total_epochs: int | None = None
    metrics: dict[str, float | None] = field(default_factory=dict)
    artifacts: dict[str, str | None] = field(default_factory=dict)
