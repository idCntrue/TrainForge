from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import cv2


@contextmanager
def open_video(path: Path) -> Iterator[cv2.VideoCapture]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        raise ValueError(f"video cannot be decoded: {path}")
    try:
        yield capture
    finally:
        capture.release()


def write_jpeg(path: Path, image: object, quality: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = cv2.imwrite(
        str(path),
        image,
        [cv2.IMWRITE_JPEG_QUALITY, quality],
    )
    if not written:
        raise OSError(f"failed to write JPEG: {path}")

