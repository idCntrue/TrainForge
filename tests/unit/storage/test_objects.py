from pathlib import Path

import pytest

from yolo_factory.storage.objects import LocalObjectStorage


def test_local_storage_writes_reads_sizes_and_deletes(tmp_path: Path) -> None:
    storage = LocalObjectStorage(tmp_path)
    stored = storage.put_bytes("frames/one.jpg", b"image")

    assert stored.key == "frames/one.jpg"
    assert stored.size_bytes == 5
    assert storage.open_path(stored.key).read_bytes() == b"image"
    assert storage.exists(stored.key)
    assert storage.size(stored.key) == 5

    storage.delete(stored.key)
    storage.delete(stored.key)
    assert not storage.exists(stored.key)


@pytest.mark.parametrize("key", ["../escape.jpg", "/absolute.jpg", r"frames\escape.jpg", "C:/escape.jpg"])
def test_local_storage_rejects_unsafe_keys(tmp_path: Path, key: str) -> None:
    storage = LocalObjectStorage(tmp_path)
    with pytest.raises(ValueError, match="storage key"):
        storage.put_bytes(key, b"image")
