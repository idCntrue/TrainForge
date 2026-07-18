from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrameLifecycleMigrationReport:
    added_columns: int


_COLUMNS = {
    "lifecycle_status": "TEXT NOT NULL DEFAULT 'active'",
    "pre_trash_status": "TEXT",
    "trashed_at": "DATETIME",
    "purge_after": "DATETIME",
    "storage_provider": "TEXT NOT NULL DEFAULT 'local'",
    "storage_key": "TEXT",
    "size_bytes": "BIGINT NOT NULL DEFAULT 0",
}


def migrate_frame_lifecycle(database: Path) -> FrameLifecycleMigrationReport:
    if not database.is_file():
        return FrameLifecycleMigrationReport(0)
    added = 0
    with sqlite3.connect(database) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='frame_assets'"
        ).fetchone()
        if table is None:
            return FrameLifecycleMigrationReport(0)
        existing = {str(row[1]) for row in connection.execute("PRAGMA table_info(frame_assets)")}
        for name, declaration in _COLUMNS.items():
            if name not in existing:
                connection.execute(f'ALTER TABLE frame_assets ADD COLUMN "{name}" {declaration}')
                added += 1
        connection.execute(
            "UPDATE frame_assets SET lifecycle_status='active' WHERE lifecycle_status IS NULL OR lifecycle_status=''"
        )
        connection.execute(
            "UPDATE frame_assets SET storage_provider='local' WHERE storage_provider IS NULL OR storage_provider=''"
        )
        connection.execute(
            "UPDATE frame_assets SET storage_key=stored_path WHERE storage_key IS NULL OR storage_key=''"
        )
        connection.execute("UPDATE frame_assets SET size_bytes=0 WHERE size_bytes IS NULL")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_frame_assets_lifecycle_status ON frame_assets(lifecycle_status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_frame_assets_purge_after ON frame_assets(purge_after)"
        )
    return FrameLifecycleMigrationReport(added)

