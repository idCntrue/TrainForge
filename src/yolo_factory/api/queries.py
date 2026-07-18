from pathlib import Path
import yaml

from sqlalchemy import func, select

from yolo_factory.api.schemas import (
    DashboardSummary,
    DatasetReleaseSummary,
    TaskSummary,
    VideoCollectionSummary,
)
from yolo_factory.api.task_metadata import decode_task_classes
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import (
    AnnotationExport,
    DatasetRelease,
    FrameBatch,
    Task,
    VideoAsset,
    VideoCollection,
)


def dashboard_summary(registry: Registry) -> DashboardSummary:
    models = (
        Task,
        VideoCollection,
        VideoAsset,
        FrameBatch,
        AnnotationExport,
        DatasetRelease,
    )
    with session_scope(registry) as session:
        counts = [session.scalar(select(func.count()).select_from(model)) for model in models]
    return DashboardSummary(
        tasks=counts[0] or 0,
        video_collections=counts[1] or 0,
        video_assets=counts[2] or 0,
        frame_batches=counts[3] or 0,
        annotation_exports=counts[4] or 0,
        dataset_releases=counts[5] or 0,
    )


def list_tasks(registry: Registry) -> list[TaskSummary]:
    with session_scope(registry) as session:
        tasks = list(session.scalars(select(Task).order_by(Task.id)))
    result = []
    for task in tasks:
        classes, display_names = decode_task_classes(task.classes_json)
        result.append(TaskSummary(
            id=task.id,
            task_type=task.task_type,
            annotation_format=task.annotation_format,
            classes=classes,
            class_display_names=display_names,
            created_at=task.created_at,
        ))
    return result


def list_video_collections(registry: Registry) -> list[VideoCollectionSummary]:
    with session_scope(registry) as session:
        statement = (
            select(
                VideoCollection,
                func.count(VideoAsset.id),
                func.coalesce(func.sum(VideoAsset.size_bytes), 0),
            )
            .outerjoin(VideoAsset, VideoAsset.collection_id == VideoCollection.id)
            .group_by(VideoCollection.id)
            .order_by(VideoCollection.created_at.desc())
        )
        rows = list(session.execute(statement))
    return [
        VideoCollectionSummary(
            id=collection.id,
            task_id=collection.task_id,
            asset_count=asset_count,
            total_size_bytes=total_size,
            created_at=collection.created_at,
        )
        for collection, asset_count, total_size in rows
    ]


def list_dataset_releases(registry: Registry, storage_root: Path | None = None) -> list[DatasetReleaseSummary]:
    with session_scope(registry) as session:
        releases = list(
            session.scalars(
                select(DatasetRelease).order_by(DatasetRelease.created_at.desc())
            )
        )
    result = []
    for release in releases:
        manifest = {}
        if storage_root is not None:
            manifest_path = storage_root / release.release_path / "manifest.yaml"
            if manifest_path.is_file():
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        result.append(DatasetReleaseSummary(
            id=release.id,
            task_id=release.task_id,
            annotation_export_id=release.annotation_export_id,
            display_name=release.display_name or release.task_id,
            version=release.version,
            status=release.status,
            release_path=release.release_path,
            requested_ratios=manifest.get("requested_ratios"),
            actual_ratios=manifest.get("actual_ratios", {}),
            split_counts=manifest.get("split_counts", {}),
            split_seed=manifest.get("split_seed"),
            grouping_strategy=manifest.get("grouping_strategy"),
            created_at=release.created_at,
        ))
    return result


def registered_video_path(
    registry: Registry,
    storage_root: Path,
    video_id: str,
) -> Path | None:
    with session_scope(registry) as session:
        video = session.get(VideoAsset, video_id)
        stored_path = video.stored_path if video is not None else None
    if stored_path is None:
        return None
    root = storage_root.resolve()
    candidate = (root / stored_path).resolve()
    if candidate != root and root not in candidate.parents:
        return None
    return candidate if candidate.is_file() else None
