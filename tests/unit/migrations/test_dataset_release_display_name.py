import sqlite3
from pathlib import Path

from yolo_factory.migrations.dataset_release_display_name import migrate_dataset_release_display_name
from yolo_factory.registry.database import create_registry


def test_adds_nullable_display_name_to_legacy_releases_idempotently(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE dataset_releases (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, version TEXT NOT NULL)"
        )
        connection.execute("INSERT INTO dataset_releases VALUES ('dataset-1', 'inspection', '0.1.0')")

    first = migrate_dataset_release_display_name(database)
    second = migrate_dataset_release_display_name(database)

    assert first.added_columns == 1
    assert second.added_columns == 0
    with sqlite3.connect(database) as connection:
        columns = {str(row[1]): row for row in connection.execute("PRAGMA table_info(dataset_releases)")}
        row = connection.execute(
            "SELECT id, task_id, version, display_name FROM dataset_releases"
        ).fetchone()
    assert columns["display_name"][3] == 0
    assert row == ("dataset-1", "inspection", "0.1.0", None)


def test_registry_startup_runs_dataset_release_migration(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE dataset_releases (id TEXT PRIMARY KEY, task_id TEXT NOT NULL, version TEXT NOT NULL)"
        )

    create_registry(database)

    with sqlite3.connect(database) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(dataset_releases)")}
    assert "display_name" in columns
