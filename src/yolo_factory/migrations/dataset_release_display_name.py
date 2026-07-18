from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetReleaseDisplayNameMigrationReport:
    added_columns: int


def migrate_dataset_release_display_name(
    database: Path,
) -> DatasetReleaseDisplayNameMigrationReport:
    if not database.is_file():
        return DatasetReleaseDisplayNameMigrationReport(0)
    with sqlite3.connect(database) as connection:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dataset_releases'"
        ).fetchone()
        if table is None:
            return DatasetReleaseDisplayNameMigrationReport(0)
        existing = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(dataset_releases)")
        }
        if "display_name" in existing:
            return DatasetReleaseDisplayNameMigrationReport(0)
        connection.execute(
            'ALTER TABLE dataset_releases ADD COLUMN "display_name" VARCHAR(200)'
        )
    return DatasetReleaseDisplayNameMigrationReport(1)
