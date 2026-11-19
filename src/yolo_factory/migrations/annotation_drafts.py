from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AnnotationDraftMigrationReport:
    altered: bool
    shapes: int


_SHAPE_COLUMNS = {
    "status": "TEXT NOT NULL DEFAULT 'confirmed'",
    "confidence": "REAL",
    "model_source": "TEXT",
    "prelabel_job_id": "TEXT",
}

_PRELABEL_RUNS_SQL = """
CREATE TABLE IF NOT EXISTS prelabel_runs (
    id VARCHAR(64) PRIMARY KEY,
    job_id VARCHAR(64),
    batch_id VARCHAR(160),
    task_id VARCHAR(128) NOT NULL,
    model_source VARCHAR(200) NOT NULL,
    model_name VARCHAR(200) NOT NULL,
    confidence FLOAT NOT NULL,
    iou FLOAT NOT NULL,
    status VARCHAR(24) NOT NULL,
    frames_total INTEGER NOT NULL DEFAULT 0,
    frames_processed INTEGER NOT NULL DEFAULT 0,
    frames_skipped INTEGER NOT NULL DEFAULT 0,
    shapes_created INTEGER NOT NULL DEFAULT 0,
    unmapped_classes_json TEXT,
    error TEXT,
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""


def migrate_annotation_drafts(database: Path) -> AnnotationDraftMigrationReport:
    if not database.is_file():
        return AnnotationDraftMigrationReport(False, 0)
    connection = sqlite3.connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='annotation_shapes'"
        ).fetchone()
        if table is None:
            connection.commit()
            return AnnotationDraftMigrationReport(False, 0)
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(annotation_shapes)")}
        altered = False
        for name, ddl in _SHAPE_COLUMNS.items():
            if name in columns:
                continue
            connection.execute(f"ALTER TABLE annotation_shapes ADD COLUMN {name} {ddl}")
            altered = True
        connection.execute(_PRELABEL_RUNS_SQL)
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_annotation_shapes_model_source "
            "ON annotation_shapes(model_source)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_annotation_shapes_status "
            "ON annotation_shapes(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS ix_prelabel_runs_task_id ON prelabel_runs(task_id)"
        )
        shapes = int(connection.execute("SELECT COUNT(*) FROM annotation_shapes").fetchone()[0])
        connection.commit()
        return AnnotationDraftMigrationReport(altered, shapes)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
