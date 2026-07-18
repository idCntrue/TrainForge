from dataclasses import dataclass
from pathlib import Path

import cv2

from yolo_factory.integrations.opencv import open_video


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    frame_count: int
    duration_ms: int


def inspect_video(path: Path) -> VideoInfo:
    with open_video(path) as capture:
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

    if width <= 0 or height <= 0:
        raise ValueError(f"video has invalid dimensions: {path}")
    if fps <= 0:
        raise ValueError(f"video has invalid fps: {path}")
    if frame_count <= 0:
        raise ValueError(f"video has no frames: {path}")

    return VideoInfo(
        width=width,
        height=height,
        fps=fps,
        frame_count=frame_count,
        duration_ms=round(frame_count / fps * 1000),
    )

