from dataclasses import dataclass
from pathlib import Path

from yolo_factory.common.hashing import sha256_file
from yolo_factory.integrations.opencv import open_video, write_jpeg
from yolo_factory.video.inspection import inspect_video


@dataclass(frozen=True)
class ExtractedFrame:
    path: Path
    sha256: str
    source_video_sha256: str
    timestamp_ms: int
    frame_index: int
    width: int
    height: int


def extract_interval_frames(
    video_path: Path,
    output_dir: Path,
    collection_id: str,
    video_id: str,
    interval_seconds: float,
    jpeg_quality: int = 95,
) -> list[ExtractedFrame]:
    if interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if not 1 <= jpeg_quality <= 100:
        raise ValueError("jpeg_quality must be between 1 and 100")

    info = inspect_video(video_path)
    interval_frames = max(1, round(info.fps * interval_seconds))
    source_hash = sha256_file(video_path)
    extracted: list[ExtractedFrame] = []

    with open_video(video_path) as capture:
        frame_index = 0
        while True:
            available, image = capture.read()
            if not available:
                break
            if frame_index % interval_frames == 0:
                timestamp_ms = round(frame_index / info.fps * 1000)
                filename = (
                    f"{collection_id}__{video_id}__"
                    f"t-{timestamp_ms:09d}ms__f-{frame_index:06d}.jpg"
                )
                destination = output_dir / filename
                write_jpeg(destination, image, jpeg_quality)
                extracted.append(
                    ExtractedFrame(
                        path=destination,
                        sha256=sha256_file(destination),
                        source_video_sha256=source_hash,
                        timestamp_ms=timestamp_ms,
                        frame_index=frame_index,
                        width=info.width,
                        height=info.height,
                    )
                )
            frame_index += 1

    if not extracted:
        raise ValueError(f"video produced no frames: {video_path}")
    return extracted
