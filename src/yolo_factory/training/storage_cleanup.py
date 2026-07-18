from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageCleanupResult:
    released_bytes: int = 0
    deleted_files: int = 0
    deleted_directories: int = 0
    skipped_symlinks: int = 0
    errors: tuple[str, ...] = ()


def cleanup_training_storage(
    storage_root: str | Path,
    *,
    stale_after_seconds: int = 24 * 60 * 60,
    now: float | None = None,
) -> StorageCleanupResult:
    """Remove only allowlisted, regenerable storage content before training."""
    root = Path(storage_root).resolve()
    cutoff = (time.time() if now is None else now) - stale_after_seconds
    released_bytes = 0
    deleted_files = 0
    deleted_directories = 0
    skipped_symlinks = 0
    errors: list[str] = []

    def remove_file(path: Path) -> None:
        nonlocal released_bytes, deleted_files, skipped_symlinks
        if path.is_symlink():
            skipped_symlinks += 1
            return
        try:
            size = path.stat().st_size
            path.unlink()
            released_bytes += size
            deleted_files += 1
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    def remove_tree(path: Path) -> None:
        nonlocal released_bytes, deleted_files, deleted_directories, skipped_symlinks
        if path.is_symlink():
            skipped_symlinks += 1
            return
        try:
            files = [candidate for candidate in path.rglob("*") if candidate.is_file() and not candidate.is_symlink()]
            skipped_symlinks += sum(1 for candidate in path.rglob("*") if candidate.is_symlink())
            size = sum(candidate.stat().st_size for candidate in files)
            count = len(files)
            shutil.rmtree(path)
            released_bytes += size
            deleted_files += count
            deleted_directories += 1
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    thumbnail_root = root / "thumbnails"
    if thumbnail_root.is_symlink():
        skipped_symlinks += 1
    elif thumbnail_root.is_dir():
        for child in list(thumbnail_root.iterdir()):
            if child.is_symlink():
                skipped_symlinks += 1
            elif child.is_dir():
                remove_tree(child)
            elif child.is_file():
                remove_file(child)

    for relative in ("imports/video-uploads", "imports/annotation-uploads"):
        upload_root = root / relative
        if upload_root.is_symlink():
            skipped_symlinks += 1
            continue
        if not upload_root.is_dir():
            continue
        for directory in list(upload_root.iterdir()):
            if directory.is_symlink():
                skipped_symlinks += 1
            elif directory.is_dir() and directory.stat().st_mtime < cutoff:
                remove_tree(directory)

    training_root = root / "training-runs"
    if training_root.is_symlink():
        skipped_symlinks += 1
    elif training_root.is_dir():
        for temporary in training_root.rglob("*.tmp"):
            if temporary.is_symlink():
                skipped_symlinks += 1
            elif temporary.is_file() and temporary.stat().st_mtime < cutoff:
                remove_file(temporary)

    return StorageCleanupResult(
        released_bytes=released_bytes,
        deleted_files=deleted_files,
        deleted_directories=deleted_directories,
        skipped_symlinks=skipped_symlinks,
        errors=tuple(errors),
    )
