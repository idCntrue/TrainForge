from pathlib import Path

from sqlalchemy import text

from yolo_factory.registry.database import create_registry


def test_sqlite_connections_use_concurrency_pragmas(tmp_path: Path) -> None:
    registry = create_registry(tmp_path / "factory.db")

    with registry.engine.connect() as connection:
        busy_timeout = connection.execute(text("PRAGMA busy_timeout")).scalar_one()
        synchronous = connection.execute(text("PRAGMA synchronous")).scalar_one()
        journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()

    assert busy_timeout == 5_000
    assert synchronous == 1
    assert journal_mode == "wal"
