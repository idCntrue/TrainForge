from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol


@dataclass(frozen=True)
class StoredObject:
    key: str
    size_bytes: int


class ObjectStorage(Protocol):
    def put_bytes(self, key: str, content: bytes) -> StoredObject: ...
    def open_path(self, key: str) -> Path: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...
    def size(self, key: str) -> int: ...


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        if not key or "\\" in key or Path(key).is_absolute():
            raise ValueError("unsafe storage key")
        parts = PurePosixPath(key).parts
        if any(part in {"", ".", ".."} for part in parts) or (parts and ":" in parts[0]):
            raise ValueError("unsafe storage key")
        candidate = self.root.joinpath(*parts).resolve()
        if candidate == self.root or self.root not in candidate.parents:
            raise ValueError("unsafe storage key")
        return candidate

    def put_bytes(self, key: str, content: bytes) -> StoredObject:
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_bytes(content)
        os.replace(temporary, destination)
        return StoredObject(key=key, size_bytes=len(content))

    def open_path(self, key: str) -> Path:
        return self._path(key)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def size(self, key: str) -> int:
        path = self._path(key)
        return path.stat().st_size if path.is_file() else 0
