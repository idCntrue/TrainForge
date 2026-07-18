from pathlib import Path

import cv2
import numpy as np

from yolo_factory.frames.extractor import extract_interval_frames
from yolo_factory.video.inspection import inspect_video


def _write_test_video(path: Path, fps: float = 10.0, frames: int = 20) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (64, 48),
    )
    assert writer.isOpened()
    for index in range(frames):
        image = np.full((48, 64, 3), index * 10, dtype=np.uint8)
        writer.write(image)
    writer.release()


def test_inspects_and_extracts_expected_interval_frames(tmp_path: Path) -> None:
    video = tmp_path / "source.avi"
    _write_test_video(video)

    info = inspect_video(video)
    extracted = extract_interval_frames(
        video_path=video,
        output_dir=tmp_path / "frames",
        collection_id="collection-20260713-001",
        video_id="video-test",
        interval_seconds=0.5,
    )

    assert info.width == 64
    assert info.height == 48
    assert info.fps == 10.0
    assert info.frame_count == 20
    assert info.duration_ms == 2000
    assert [frame.timestamp_ms for frame in extracted] == [0, 500, 1000, 1500]
    assert [frame.frame_index for frame in extracted] == [0, 5, 10, 15]
    assert extracted[0].path.name == (
        "collection-20260713-001__video-test__"
        "t-000000000ms__f-000000.jpg"
    )
    assert all(frame.path.exists() for frame in extracted)
    assert all(len(frame.sha256) == 64 for frame in extracted)

