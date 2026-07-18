from pathlib import Path

import pytest

from yolo_factory.frames.extractor import extract_interval_frames


@pytest.mark.parametrize("interval", [0, -1])
def test_rejects_nonpositive_interval(tmp_path: Path, interval: float) -> None:
    with pytest.raises(ValueError, match="interval"):
        extract_interval_frames(
            video_path=tmp_path / "missing.avi",
            output_dir=tmp_path / "frames",
            collection_id="collection-20260713-001",
            video_id="video-test",
            interval_seconds=interval,
        )


@pytest.mark.parametrize("quality", [0, 101])
def test_rejects_invalid_jpeg_quality(tmp_path: Path, quality: int) -> None:
    with pytest.raises(ValueError, match="quality"):
        extract_interval_frames(
            video_path=tmp_path / "missing.avi",
            output_dir=tmp_path / "frames",
            collection_id="collection-20260713-001",
            video_id="video-test",
            interval_seconds=1,
            jpeg_quality=quality,
        )
