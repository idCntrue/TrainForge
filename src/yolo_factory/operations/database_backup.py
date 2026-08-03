from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from yolo_factory.common.hashing import sha256_file
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import DatabaseBackupRecord


class DatabaseBackupError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatabaseBackup:
    id: str
    path: Path
    size_bytes: int
    sha256: str
    integrity_check: str
    created_at: datetime


def _integrity_check(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        return str(row[0]) if row else "missing"
    finally:
        connection.close()


class DatabaseBackupService:
    def __init__(
        self,
        registry: Registry,
        database: Path,
        backup_root: Path,
        *,
        retention: int,
        integrity_check: Callable[[Path], str] = _integrity_check,
    ) -> None:
        if not 1 <= retention <= 100:
            raise ValueError("backup retention must be between 1 and 100")
        self._registry = registry
        self._database = database.resolve()
        self._backup_root = backup_root.resolve()
        try:
            self._backup_root.relative_to(self._database.parent)
        except ValueError as error:
            raise ValueError("backup directory must stay below the registry directory") from error
        self._retention = retention
        self._integrity_check = integrity_check

    def create(self) -> DatabaseBackup:
        self._backup_root.mkdir(parents=True, exist_ok=True)
        backup_id = uuid.uuid4().hex
        timestamp = datetime.now(timezone.utc)
        staging = self._backup_root / f".{backup_id}.tmp"
        destination = self._backup_root / f"factory.backup-{timestamp:%Y%m%d-%H%M%S-%f}.db"
        try:
            source = sqlite3.connect(f"file:{self._database.as_posix()}?mode=ro", uri=True)
            target = sqlite3.connect(staging)
            try:
                source.backup(target)
            finally:
                target.close()
                source.close()
            integrity = self._integrity_check(staging)
            if integrity != "ok":
                raise DatabaseBackupError(f"integrity check failed: {integrity}")
            staging.replace(destination)
            digest = sha256_file(destination)
            with session_scope(self._registry) as session:
                session.add(DatabaseBackupRecord(
                    id=backup_id,
                    relative_path=destination.relative_to(self._database.parent).as_posix(),
                    size_bytes=destination.stat().st_size,
                    sha256=digest,
                    integrity_check=integrity,
                    created_at=timestamp,
                ))
            self._prune()
            return next(item for item in self.list() if item.id == backup_id)
        except Exception:
            staging.unlink(missing_ok=True)
            raise

    def list(self) -> list[DatabaseBackup]:
        with session_scope(self._registry) as session:
            records = list(session.scalars(
                select(DatabaseBackupRecord).order_by(
                    DatabaseBackupRecord.created_at.desc(), DatabaseBackupRecord.id.desc(),
                )
            ))
        return [self._to_backup(record) for record in records]

    def _prune(self) -> None:
        with session_scope(self._registry) as session:
            records = list(session.scalars(
                select(DatabaseBackupRecord).order_by(
                    DatabaseBackupRecord.created_at.desc(), DatabaseBackupRecord.id.desc(),
                )
            ))
            for record in records[self._retention:]:
                path = (self._database.parent / record.relative_path).resolve()
                if path.is_relative_to(self._backup_root):
                    path.unlink(missing_ok=True)
                session.delete(record)

    def _to_backup(self, record: DatabaseBackupRecord) -> DatabaseBackup:
        return DatabaseBackup(
            id=record.id,
            path=(self._database.parent / record.relative_path).resolve(),
            size_bytes=record.size_bytes,
            sha256=record.sha256,
            integrity_check=record.integrity_check,
            created_at=record.created_at,
        )
