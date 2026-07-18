import sqlite3
from pathlib import Path

from yolo_factory.migrations.frame_lifecycle import migrate_frame_lifecycle


def test_adds_and_backfills_frame_lifecycle_columns_idempotently(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE frame_assets (id TEXT PRIMARY KEY, stored_path TEXT NOT NULL, status TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO frame_assets VALUES ('frame-1', 'frames/one.jpg', 'selected')")

    first = migrate_frame_lifecycle(database)
    second = migrate_frame_lifecycle(database)

    assert first.added_columns == 7
    assert second.added_columns == 0
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT lifecycle_status, storage_provider, storage_key, size_bytes FROM frame_assets"
        ).fetchone()
    assert row == ("active", "local", "frames/one.jpg", 0)
