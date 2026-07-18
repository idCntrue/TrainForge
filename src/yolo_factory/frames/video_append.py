import hashlib
import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select

from yolo_factory.common.hashing import sha256_file
from yolo_factory.frames.extractor import ExtractedFrame, extract_interval_frames
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import FrameAsset, FrameBatch, Task, VideoAsset, VideoCollection
from yolo_factory.video.import_service import VIDEO_EXTENSIONS


@dataclass(frozen=True)
class VideoAppendResult:
    batch_id: str
    imported_video_count: int
    duplicate_video_count: int
    created_frame_count: int
    duplicate_frame_count: int


def _managed_directory(base: Path, *parts: str) -> Path:
    resolved_base = base.resolve()
    candidate = resolved_base.joinpath(*parts).resolve()
    try:
        candidate.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError("managed storage path escapes its root") from exc
    return candidate


def _storage_key(path: Path, storage_root: Path) -> str:
    try:
        return path.resolve().relative_to(storage_root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError("persistent asset path is outside storage root") from exc


def _video_sources(source_dir: Path) -> list[Path]:
    return sorted(
        path for path in source_dir.iterdir()
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )


def _read_manifest(path: Path) -> dict:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    return payload if isinstance(payload, dict) else {}


def _write_manifest(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    if path.suffix.lower() == ".json":
        content = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        content = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def append_videos_to_batch(
    batch_id: str,
    source_dir: Path,
    storage_root: Path,
    registry: Registry,
    *,
    interval: float,
    quality: int,
    extractor: Callable[..., list[ExtractedFrame]] = extract_interval_frames,
) -> VideoAppendResult:
    if interval <= 0:
        raise ValueError("interval must be positive")
    if not 1 <= quality <= 100:
        raise ValueError("quality must be between 1 and 100")

    with session_scope(registry) as session:
        batch = session.get(FrameBatch, batch_id)
        if batch is None:
            raise ValueError(f"unknown frame batch: {batch_id}")
        collection = session.get(VideoCollection, batch.collection_id)
        if collection is None:
            raise ValueError(f"unknown video collection: {batch.collection_id}")
        task = session.get(Task, collection.task_id)
        if task is None:
            raise ValueError(f"unknown task: {collection.task_id}")
        manifest_path = (storage_root / batch.manifest_path).resolve()
        try:
            manifest_path.relative_to(storage_root.resolve())
        except ValueError as exc:
            raise ValueError("batch manifest is outside storage root") from exc
        existing_video_hashes = set(session.scalars(
            select(VideoAsset.sha256)
            .join(VideoCollection, VideoAsset.collection_id == VideoCollection.id)
            .where(VideoCollection.task_id == task.id)
        ))
        existing_frame_hashes = set(session.scalars(
            select(FrameAsset.sha256).where(FrameAsset.batch_id == batch_id)
        ))
        collection_id = collection.id
        task_id = task.id

    videos_dir = _managed_directory(storage_root / "raw-videos", task_id, collection_id, "videos")
    candidates_dir = _managed_directory(storage_root / "frame-batches", task_id, batch_id, "candidates")
    videos_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir.mkdir(parents=True, exist_ok=True)

    imported: list[tuple[VideoAsset, Path]] = []
    duplicate_video_count = 0
    for source_path in _video_sources(source_dir):
        content_hash = sha256_file(source_path)
        if content_hash in existing_video_hashes:
            duplicate_video_count += 1
            continue
        existing_video_hashes.add(content_hash)
        video_id = f"video-{task_id}-{content_hash[:16]}"
        destination = videos_dir / f"{content_hash}{source_path.suffix.lower()}"
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copyfile(source_path, temporary)
        if sha256_file(temporary) != content_hash:
            temporary.unlink(missing_ok=True)
            raise OSError(f"copied video hash mismatch: {source_path.name}")
        temporary.replace(destination)
        imported.append((VideoAsset(
            id=video_id,
            collection_id=collection_id,
            original_name=source_path.name,
            stored_path=_storage_key(destination, storage_root),
            sha256=content_hash,
            size_bytes=destination.stat().st_size,
        ), destination))

    if imported:
        with session_scope(registry) as session:
            session.add_all([record for record, _ in imported])

    created_frames: list[FrameAsset] = []
    duplicate_frame_count = 0
    appended_history: list[dict] = []
    for video, video_path in imported:
        frames = extractor(
            video_path, candidates_dir, collection_id, video.id, interval, quality
        )
        created_for_video = 0
        duplicates_for_video = 0
        for frame in frames:
            if frame.sha256 in existing_frame_hashes:
                duplicate_frame_count += 1
                duplicates_for_video += 1
                frame.path.unlink(missing_ok=True)
                continue
            existing_frame_hashes.add(frame.sha256)
            identity = hashlib.sha256(f"{batch_id}:{frame.sha256}".encode("utf-8")).hexdigest()[:32]
            storage_key = _storage_key(frame.path, storage_root)
            created_frames.append(FrameAsset(
                id=f"frame-{identity}",
                batch_id=batch_id,
                video_id=video.id,
                stored_path=storage_key,
                sha256=frame.sha256,
                timestamp_ms=frame.timestamp_ms,
                frame_index=frame.frame_index,
                status="candidate",
                storage_key=storage_key,
                size_bytes=frame.path.stat().st_size,
            ))
            created_for_video += 1
        appended_history.append({
            "video_id": video.id,
            "original_name": video.original_name,
            "stored_path": video.stored_path,
            "sha256": video.sha256,
            "interval": interval,
            "quality": quality,
            "created_frame_count": created_for_video,
            "duplicate_frame_count": duplicates_for_video,
        })

    if created_frames:
        with session_scope(registry) as session:
            session.add_all(created_frames)

    if appended_history:
        manifest = _read_manifest(manifest_path)
        manifest.setdefault("task_id", task_id)
        manifest.setdefault("batch_id", batch_id)
        manifest.setdefault("appended_videos", []).extend(appended_history)
        _write_manifest(manifest_path, manifest)

    return VideoAppendResult(
        batch_id=batch_id,
        imported_video_count=len(imported),
        duplicate_video_count=duplicate_video_count,
        created_frame_count=len(created_frames),
        duplicate_frame_count=duplicate_frame_count,
    )
