import sqlite3
from pathlib import Path

from yolo_factory.migrations.annotation_drafts import migrate_annotation_drafts


def _legacy_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE annotation_shapes ("
            "id VARCHAR(64) PRIMARY KEY, frame_id VARCHAR(64) NOT NULL, "
            "class_id INTEGER NOT NULL, class_name VARCHAR(200) NOT NULL, "
            "shape_type VARCHAR(16) NOT NULL, coordinates_json TEXT NOT NULL, "
            "source VARCHAR(16) NOT NULL, updated_at DATETIME NOT NULL, "
            "created_at DATETIME NOT NULL)"
        )
        connection.execute(
            "INSERT INTO annotation_shapes VALUES "
            "('shape-1', 'frame-1', 0, 'red', 'box', '[0.5,0.5,0.2,0.2]', 'manual', '2026-01-01', '2026-01-01')"
        )
        connection.commit()
    finally:
        connection.close()


def test_adds_draft_columns_and_runs_table_idempotently(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    _legacy_database(database)

    first = migrate_annotation_drafts(database)
    second = migrate_annotation_drafts(database)

    assert first.altered is True
    assert first.shapes == 1
    assert second.altered is False

    connection = sqlite3.connect(database)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(annotation_shapes)")}
        assert {"status", "confidence", "model_source", "prelabel_job_id"} <= columns
        assert connection.execute("SELECT status FROM annotation_shapes").fetchone()[0] == "confirmed"
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='prelabel_runs'"
        ).fetchone() is not None
    finally:
        connection.close()


def test_missing_database_is_a_noop(tmp_path: Path) -> None:
    report = migrate_annotation_drafts(tmp_path / "missing.db")

    assert report.altered is False
    assert report.shapes == 0
