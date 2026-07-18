from dataclasses import dataclass
from pathlib import Path
from shutil import copyfileobj

from sqlalchemy import select

from yolo_factory.common.hashing import sha256_file
from yolo_factory.manifests.writer import write_manifest
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import Task, VideoAsset, VideoCollection

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".m4v"}


@dataclass(frozen=True)
class VideoImportResult:
    collection_id: str
    imported_count: int
    duplicate_count: int
    manifest_path: Path


def _video_sources(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def import_video_collection(
    task_id: str,
    collection_id: str,
    source_dir: Path,
    storage_root: Path,
    registry: Registry,
) -> VideoImportResult:
    with session_scope(registry) as session:
        if session.get(Task, task_id) is None:
            raise ValueError(f"unknown task: {task_id}")
        if session.get(VideoCollection, collection_id) is not None:
            raise ValueError(f"collection already exists: {collection_id}")
        existing_hashes = set(session.scalars(
            select(VideoAsset.sha256)
            .join(VideoCollection, VideoAsset.collection_id == VideoCollection.id)
            .where(VideoCollection.task_id == task_id)
        ).all())

    collection_root = storage_root / "raw-videos" / task_id / collection_id
    videos_dir = collection_root / "videos"
    manifest_path = collection_root / "manifest.yaml"
    videos_dir.mkdir(parents=True, exist_ok=True)

    imported: list[dict[str, object]] = []
    duplicates: list[dict[str, str]] = []
    asset_rows: list[VideoAsset] = []
    created_paths: list[Path] = []
    try:
        for source_path in _video_sources(source_dir):
            content_hash = sha256_file(source_path)
            if content_hash in existing_hashes:
                duplicates.append({"original_name": source_path.name, "sha256": content_hash})
                continue
            existing_hashes.add(content_hash)

            video_id = f"video-{task_id}-{content_hash[:16]}"
            destination = videos_dir / f"{content_hash}{source_path.suffix.lower()}"
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            with source_path.open("rb") as source_stream:
                with temporary.open("wb") as destination_stream:
                    copyfileobj(source_stream, destination_stream)
            if sha256_file(temporary) != content_hash:
                raise OSError(f"copied video hash mismatch: {source_path}")
            existed = destination.exists()
            temporary.replace(destination)
            if not existed:
                created_paths.append(destination)

            relative_path = destination.relative_to(storage_root).as_posix()
            asset_rows.append(VideoAsset(
                id=video_id,
                collection_id=collection_id,
                original_name=source_path.name,
                stored_path=relative_path,
                sha256=content_hash,
                size_bytes=destination.stat().st_size,
            ))
            imported.append({
                "id": video_id,
                "original_name": source_path.name,
                "stored_path": relative_path,
                "sha256": content_hash,
                "size_bytes": destination.stat().st_size,
            })

        with session_scope(registry) as session:
            session.add(VideoCollection(id=collection_id, task_id=task_id))
            session.flush()
            session.add_all(asset_rows)
    except Exception:
        for temporary in videos_dir.glob("*.tmp"):
            temporary.unlink(missing_ok=True)
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise

    write_manifest(
        manifest_path,
        {
            "collection_id": collection_id,
            "task_id": task_id,
            "videos": imported,
            "duplicates": duplicates,
        },
    )
    return VideoImportResult(
        collection_id=collection_id,
        imported_count=len(imported),
        duplicate_count=len(duplicates),
        manifest_path=manifest_path,
    )
