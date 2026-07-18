from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=utc_now, nullable=False)


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(16), nullable=False)
    annotation_format: Mapped[str] = mapped_column(String(32), nullable=False)
    classes_json: Mapped[str] = mapped_column(Text, nullable=False)


class VideoCollection(Base, TimestampMixin):
    __tablename__ = "video_collections"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class VideoAsset(Base, TimestampMixin):
    __tablename__ = "video_assets"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("video_collections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)


class FrameBatch(Base, TimestampMixin):
    __tablename__ = "frame_batches"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("video_collections.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    manifest_path: Mapped[str] = mapped_column(Text, nullable=False)


class FrameAsset(Base, TimestampMixin):
    __tablename__ = "frame_assets"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("frame_batches.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    video_id: Mapped[str] = mapped_column(
        ForeignKey("video_assets.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    frame_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    rejection_reason: Mapped[str | None] = mapped_column(String(64))
    lifecycle_status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    pre_trash_status: Mapped[str | None] = mapped_column(String(32))
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    storage_provider: Mapped[str] = mapped_column(String(16), nullable=False, default="local")
    storage_key: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class AnnotationImageRecord(Base, TimestampMixin):
    __tablename__ = "annotation_images"

    frame_id: Mapped[str] = mapped_column(ForeignKey("frame_assets.id", ondelete="RESTRICT"), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="RESTRICT"), nullable=False, index=True)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)


class AnnotationShapeRecord(Base, TimestampMixin):
    __tablename__ = "annotation_shapes"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    frame_id: Mapped[str] = mapped_column(ForeignKey("annotation_images.frame_id", ondelete="CASCADE"), nullable=False, index=True)
    class_id: Mapped[int] = mapped_column(Integer, nullable=False)
    class_name: Mapped[str] = mapped_column(String(160), nullable=False)
    shape_type: Mapped[str] = mapped_column(String(16), nullable=False)
    coordinates_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)


class AnnotationExport(Base, TimestampMixin):
    __tablename__ = "annotation_exports"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    provider_project: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_version: Mapped[str] = mapped_column(String(64), nullable=False)
    zip_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class DatasetRelease(Base, TimestampMixin):
    __tablename__ = "dataset_releases"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    annotation_export_id: Mapped[str] = mapped_column(
        ForeignKey("annotation_exports.id", ondelete="RESTRICT"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    release_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class TrainingRunRecord(Base, TimestampMixin):
    __tablename__ = "training_runs"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    dataset_release_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_releases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    base_model: Mapped[str] = mapped_column(String(200), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    phase: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    message: Mapped[str] = mapped_column(Text, nullable=False, default="Queued")
    pid: Mapped[int | None] = mapped_column(Integer)
    run_directory: Mapped[str | None] = mapped_column(Text)
    heartbeat_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    exit_code: Mapped[int | None] = mapped_column(Integer)
    cancel_requested_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class ModelVersionRecord(Base, TimestampMixin):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    task_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    training_run_id: Mapped[str] = mapped_column(ForeignKey("training_runs.id", ondelete="RESTRICT"), nullable=False, unique=True)
    dataset_release_id: Mapped[str] = mapped_column(ForeignKey("dataset_releases.id", ondelete="RESTRICT"), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, default="candidate")
    gates_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    gate_report_path: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None]
    archived_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)


class InferenceRunRecord(Base, TimestampMixin):
    __tablename__ = "inference_runs"

    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    model_version_id: Mapped[str] = mapped_column(ForeignKey("model_versions.id", ondelete="RESTRICT"), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    runtime: Mapped[str] = mapped_column(String(16), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    progress: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    output_directory: Mapped[str | None] = mapped_column(Text)
    result_path: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[datetime | None]
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now, nullable=False)
