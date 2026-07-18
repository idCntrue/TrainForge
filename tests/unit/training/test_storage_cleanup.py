import os
import time
from pathlib import Path

from yolo_factory.training.storage_cleanup import cleanup_training_storage


def _age(path: Path, *, hours: int) -> None:
    timestamp = time.time() - hours * 60 * 60
    os.utime(path, (timestamp, timestamp))


def test_cleanup_removes_only_regenerable_and_stale_temporary_content(tmp_path: Path) -> None:
    thumbnail = tmp_path / "thumbnails" / "annotations" / "frame.jpg"
    thumbnail.parent.mkdir(parents=True)
    thumbnail.write_bytes(b"cache")

    stale_upload = tmp_path / "imports" / "video-uploads" / "stale" / "video.mp4"
    stale_upload.parent.mkdir(parents=True)
    stale_upload.write_bytes(b"temporary upload")
    _age(stale_upload, hours=25)
    _age(stale_upload.parent, hours=25)

    fresh_upload = tmp_path / "imports" / "annotation-uploads" / "active" / "labels.zip"
    fresh_upload.parent.mkdir(parents=True)
    fresh_upload.write_bytes(b"active")

    stale_tmp = tmp_path / "training-runs" / "run-1" / "progress.json.tmp"
    stale_tmp.parent.mkdir(parents=True)
    stale_tmp.write_bytes(b"partial")
    _age(stale_tmp, hours=25)

    protected = [
        tmp_path / "registry" / "factory.db",
        tmp_path / "dataset-releases" / "task" / "data.yaml",
        tmp_path / "frame-batches" / "task" / "batch" / "selected" / "image.jpg",
        tmp_path / "model-weights" / "uploads" / "weight" / "best.pt",
        tmp_path / "training-runs" / "run-1" / "ultralytics" / "weights" / "best.pt",
    ]
    for path in protected:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"protected")

    result = cleanup_training_storage(tmp_path, stale_after_seconds=24 * 60 * 60)

    assert not thumbnail.exists()
    assert not stale_upload.parent.exists()
    assert not stale_tmp.exists()
    assert fresh_upload.exists()
    assert all(path.exists() for path in protected)
    assert result.released_bytes == len(b"cache") + len(b"temporary upload") + len(b"partial")
    assert result.deleted_files == 3
    assert result.errors == ()


def test_cleanup_does_not_follow_symlinked_temporary_roots(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "keep.db"
    secret.write_bytes(b"database")
    link = tmp_path / "thumbnails"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        return

    result = cleanup_training_storage(tmp_path)

    assert secret.exists()
    assert result.deleted_files == 0
    assert result.skipped_symlinks == 1
