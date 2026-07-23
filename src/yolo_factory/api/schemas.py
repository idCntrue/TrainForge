from datetime import datetime
from typing import Any, List, Optional, Dict, Literal
from pydantic import BaseModel, Field, model_validator


class DashboardSummary(BaseModel):
    tasks: int
    video_collections: int
    video_assets: int
    frame_batches: int
    annotation_exports: int
    dataset_releases: int


class TaskSummary(BaseModel):
    id: str
    task_type: str
    annotation_format: str
    classes: List[str]
    class_display_names: Dict[str, str] = Field(default_factory=dict)
    created_at: datetime


class TaskCreateRequest(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=128)
    task_type: str = Field(pattern=r"^(detect|segment)$")
    classes: List[str] = Field(min_length=1)
    class_display_names: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_classes(self) -> "TaskCreateRequest":
        normalized = [name.strip() for name in self.classes]
        if any(not name for name in normalized):
            raise ValueError("class names must not be blank")
        if len(set(normalized)) != len(normalized):
            raise ValueError("class names must be unique")
        unknown = set(self.class_display_names) - set(normalized)
        if unknown:
            raise ValueError("class display names must target declared classes")
        self.class_display_names = {
            key: value.strip() for key, value in self.class_display_names.items() if value.strip()
        }
        self.classes = normalized
        return self


class TaskUpdateRequest(BaseModel):
    class_display_names: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_display_names(self) -> "TaskUpdateRequest":
        self.class_display_names = {
            key: value.strip() for key, value in self.class_display_names.items() if value.strip()
        }
        return self


class VideoCollectionSummary(BaseModel):
    id: str
    task_id: str
    asset_count: int
    total_size_bytes: int
    created_at: datetime


class DatasetReleaseSummary(BaseModel):
    id: str
    display_name: str
    task_id: str
    annotation_export_id: str
    version: str
    status: str
    release_path: str
    requested_ratios: Optional[Dict[str, int]] = None
    actual_ratios: Dict[str, float] = Field(default_factory=dict)
    split_counts: Dict[str, int] = Field(default_factory=dict)
    split_seed: Optional[int] = None
    grouping_strategy: Optional[str] = None
    created_at: datetime


class DatasetReconciliationFindingResponse(BaseModel):
    key: str
    release_id: Optional[str] = None
    release_path: str
    task_id: Optional[str] = None
    version: Optional[str] = None
    database_exists: bool
    directory_exists: bool
    manifest_valid: bool
    checksums_valid: bool
    status: str
    message: str
    allowed_actions: List[str] = Field(default_factory=list)


class DatasetReconciliationRegisterRequest(BaseModel):
    release_path: str = Field(min_length=1, max_length=1024)


class VideoImportRequest(BaseModel):
    task_id: str
    collection_id: str
    source_dir: str


class FrameExtractRequest(BaseModel):
    collection_id: str
    batch_id: str
    interval: float = 1.0
    quality: int = 95


class FrameAssetSummary(BaseModel):
    id: str
    filename: str
    stored_path: str
    status: str
    rejection_reason: Optional[str] = None
    timestamp_ms: int
    frame_index: int
    video_id: str


class FrameStatusCounts(BaseModel):
    candidate: int = 0
    selected: int = 0
    rejected: int = 0
    duplicate: int = 0


class FramePageResponse(BaseModel):
    items: List[FrameAssetSummary]
    page: int
    page_size: int
    total: int
    status_counts: FrameStatusCounts


class BulkFrameSelection(BaseModel):
    mode: Literal["explicit", "all_matching"]
    ids: List[str] = Field(default_factory=list)
    status: Optional[Literal["candidate", "selected", "rejected", "duplicate"]] = None
    search: str = ""
    excluded_ids: List[str] = Field(default_factory=list)


class BulkFrameSelectionRequest(BaseModel):
    selection: BulkFrameSelection
    target_status: str = Field(pattern=r"^(candidate|selected|rejected/(blur|no-target|privacy|duplicate|other))$")


class FrameTrashRequest(BulkFrameSelection):
    request_id: str = Field(min_length=8, max_length=128)


class RecycleMutationRequest(BaseModel):
    ids: List[str] = Field(min_length=1)
    request_id: str = Field(min_length=8, max_length=128)


class RecyclePurgeRequest(RecycleMutationRequest):
    confirm_count: int = Field(ge=1)


class DuplicateGroupSummary(BaseModel):
    canonical: str
    duplicates: List[str]


class SelectionUpdateRequest(BaseModel):
    selections: Dict[str, str]  # filename -> status (e.g. "selected", "rejected/blur")


class AnnotationImportRequest(BaseModel):
    task_id: str
    archive_path: str
    project: str
    provider_version: str


class SplitRatiosRequest(BaseModel):
    train: int = Field(ge=0, le=100)
    val: int = Field(ge=0, le=100)
    test: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def validate_total(self) -> "SplitRatiosRequest":
        if self.train + self.val + self.test != 100:
            raise ValueError("split ratios must total 100")
        return self


class DatasetReleaseRequest(BaseModel):
    task_id: str
    annotation_import_id: str
    display_name: str = Field(min_length=1, max_length=200)
    version: str
    split_ratios: SplitRatiosRequest = Field(default_factory=lambda: SplitRatiosRequest(train=70, val=20, test=10))
    split_seed: int = 42

    @model_validator(mode="after")
    def normalize_display_name(self) -> "DatasetReleaseRequest":
        self.display_name = self.display_name.strip()
        if not self.display_name:
            raise ValueError("dataset display name must not be blank")
        return self


class TrainingAugmentationOptions(BaseModel):
    mosaic: float = Field(default=1.0, ge=0.0, le=1.0)
    mixup: float = Field(default=0.0, ge=0.0, le=1.0)
    copy_paste: float = Field(default=0.0, ge=0.0, le=1.0)
    degrees: float = Field(default=0.0, ge=0.0, le=45.0)
    translate: float = Field(default=0.1, ge=0.0, le=0.5)
    scale: float = Field(default=0.5, ge=0.0, le=0.9)
    fliplr: float = Field(default=0.5, ge=0.0, le=1.0)
    hsv_h: float = Field(default=0.015, ge=0.0, le=0.1)
    hsv_s: float = Field(default=0.7, ge=0.0, le=1.0)
    hsv_v: float = Field(default=0.4, ge=0.0, le=1.0)


class TrainingRunCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    task_type: str
    dataset_release_id: str = Field(min_length=1, max_length=160)
    base_model: str = Field(min_length=1, max_length=200)
    epochs: int = Field(default=100, ge=1, le=10_000)
    batch: int = Field(default=1, ge=1, le=1024)
    image_size: int = Field(default=320, ge=32, le=4096, multiple_of=32)
    device: str = Field(default="cpu", min_length=1, max_length=64)
    selected_classes: list[str] = Field(default_factory=list)
    class_aliases: dict[str, str] = Field(default_factory=dict)
    preset_id: str = Field(default="custom", pattern="^(custom|smoke|cpu-balanced|gpu-quality)$")
    patience: int = Field(default=20, ge=0, le=10_000)
    optimizer: str = Field(default="auto", pattern="^(auto|SGD|Adam|AdamW)$")
    close_mosaic: int = Field(default=10, ge=0, le=10_000)
    augment_profile: str = Field(default="standard", pattern="^(conservative|standard)$")
    augmentation: TrainingAugmentationOptions = Field(default_factory=TrainingAugmentationOptions)

    @model_validator(mode="after")
    def validate_training_strategy(self) -> "TrainingRunCreateRequest":
        if "close_mosaic" in self.model_fields_set and self.close_mosaic > self.epochs:
            raise ValueError("close_mosaic must not exceed epochs")
        return self


class TrainingRetryRequest(BaseModel):
    strategy: str = Field(pattern="^safe$")
    request_id: str = Field(min_length=8, max_length=128)


class TrainingRunResponse(BaseModel):
    id: str
    name: str
    task_type: str
    dataset_release_id: str
    base_model: str
    epochs: int
    batch: int
    image_size: int
    device: str
    status: str
    progress: float
    phase: str
    message: str
    pid: int | None
    run_directory: str | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    exit_code: int | None
    selected_classes: list[str]
    class_aliases: dict[str, str]
    epoch: int | None
    total_epochs: int | None
    metrics: dict[str, float | None]
    artifacts: dict[str, str | None]
    source_run_id: str | None = None
    execution_mode: str = "train"
    retry_strategy: str | None = None
    preset_id: str = "custom"
    patience: int = 20
    optimizer: str = "auto"
    close_mosaic: int = 10
    augment_profile: str = "standard"
    augmentation: dict[str, float] = Field(default_factory=dict)


class ModelVersionCreateRequest(BaseModel):
    training_run_id: str
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=64)


class ModelVersionResponse(BaseModel):
    id: str
    name: str
    version: str
    task_type: str
    training_run_id: str
    dataset_release_id: str
    selected_classes: list[str]
    class_aliases: dict[str, str]
    metrics: dict[str, float | None]
    status: str
    gates: dict[str, bool]
    artifacts: dict[str, dict]
    environment: dict[str, str]
    gate_report_path: str | None
    quality_report: dict | None = None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
    archived_at: datetime | None


class ModelGateReportResponse(BaseModel):
    available: bool
    report: dict | None = None
    reason: str | None = None


class ImportedModelResponse(BaseModel):
    id: str
    name: str
    task_type: str
    artifact_format: str
    original_name: str
    artifact: dict[str, Any]
    status: str
    class_names: list[str]
    created_at: datetime
    updated_at: datetime


class InferenceRunCreateRequest(BaseModel):
    model_version_id: str | None = Field(default=None, min_length=1, max_length=160)
    imported_model_id: str | None = Field(default=None, min_length=1, max_length=160)
    mode: str
    runtime: str
    sources: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_model_source(self) -> "InferenceRunCreateRequest":
        if (self.model_version_id is None) == (self.imported_model_id is None):
            raise ValueError("exactly one inference model source is required")
        return self


class InferenceRunResponse(BaseModel):
    id: str
    model_version_id: str | None
    imported_model_id: str | None
    mode: str
    runtime: str
    sources: list[str]
    confidence: float
    status: str
    progress: float
    message: str
    output_directory: str | None
    result_path: str | None
    result: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class AnnotationSyncRequest(BaseModel):
    task_id: str


class AnnotationShapeMutationRequest(BaseModel):
    revision: int = Field(ge=0)
    class_id: int = Field(ge=0)
    class_name: str
    shape_type: str
    coordinates: list[float]
    source: str = "manual"


class AnnotationStatusRequest(BaseModel):
    revision: int = Field(ge=0)
    status: str


class AnnotationShapeResponse(BaseModel):
    id: str
    class_id: int
    class_name: str
    shape_type: str
    coordinates: list[float]
    source: str
    created_at: datetime
    updated_at: datetime


class AnnotationImageResponse(BaseModel):
    frame_id: str
    task_id: str
    task_type: str
    image_path: str
    width: int
    height: int
    status: str
    revision: int
    classes: list[str]
    shapes: list[AnnotationShapeResponse]
    created_at: datetime
    updated_at: datetime


class AnnotationImageSummaryResponse(BaseModel):
    frame_id: str
    task_id: str
    task_type: str
    status: str
    revision: int
    shape_count: int
    created_at: datetime
    updated_at: datetime


class AnnotationImagePageResponse(BaseModel):
    items: list[AnnotationImageSummaryResponse]
    page: int
    page_size: int
    total: int
    status_counts: dict[str, int]


class AnnotationSyncResponse(BaseModel):
    synced_count: int
    total_count: int


class NativeAnnotationExportRequest(BaseModel):
    task_id: str
    export_name: str = Field(min_length=1, max_length=64)


class SamSuggestionRequest(BaseModel):
    revision: int = Field(ge=0)
    class_id: int = Field(ge=0)
    class_name: str
    model: str
    point: list[float] = Field(min_length=2, max_length=2)


class SamPreviewRequest(BaseModel):
    model: str
    positive_points: list[list[float]] = Field(min_length=1)
    negative_points: list[list[float]] = Field(default_factory=list)
    simplify: float = Field(0.2, ge=0, le=1)

    @model_validator(mode="after")
    def validate_points(self) -> "SamPreviewRequest":
        points = self.positive_points + self.negative_points
        if any(len(point) != 2 or any(value < 0 or value > 1 for value in point) for point in points):
            raise ValueError("SAM points must be normalized to [0, 1]")
        return self
