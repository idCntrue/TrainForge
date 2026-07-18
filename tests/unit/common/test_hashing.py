from hashlib import sha256
from pathlib import Path

from yolo_factory.common.hashing import sha256_file


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "sample.bin"
    path.write_bytes(b"video-content")

    assert sha256_file(path) == sha256(b"video-content").hexdigest()

