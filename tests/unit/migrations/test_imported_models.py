import sqlite3
from pathlib import Path

from yolo_factory.migrations.imported_models import migrate_imported_models


def _legacy_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            PRAGMA foreign_keys=ON;
            CREATE TABLE model_versions (id TEXT PRIMARY KEY);
            INSERT INTO model_versions VALUES ('model-1');
            CREATE TABLE inference_runs (
                id VARCHAR(160) PRIMARY KEY,
                model_version_id VARCHAR(160) NOT NULL REFERENCES model_versions(id) ON DELETE RESTRICT,
                mode VARCHAR(16) NOT NULL,
                runtime VARCHAR(16) NOT NULL,
                config_json TEXT NOT NULL,
                status VARCHAR(32) NOT NULL,
                progress FLOAT NOT NULL,
                message TEXT NOT NULL,
                output_directory TEXT,
                result_path TEXT,
                finished_at DATETIME,
                updated_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL
            );
            CREATE INDEX ix_inference_runs_model_version_id ON inference_runs(model_version_id);
            CREATE INDEX ix_inference_runs_status ON inference_runs(status);
            INSERT INTO inference_runs VALUES (
                'run-1', 'model-1', 'image', 'pt', '{}', 'completed', 100, 'Completed',
                NULL, NULL, NULL, '2026-07-20', '2026-07-20'
            );
        """)


def test_migrates_legacy_inference_rows_without_losing_registered_model_reference(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    _legacy_database(database)

    first = migrate_imported_models(database)
    second = migrate_imported_models(database)

    assert first.rebuilt_inference_runs is True
    assert first.preserved_rows == 1
    assert second.rebuilt_inference_runs is False
    with sqlite3.connect(database) as connection:
        columns = {row[1]: row for row in connection.execute("PRAGMA table_info(inference_runs)")}
        row = connection.execute(
            "SELECT id, model_version_id, imported_model_id, status FROM inference_runs"
        ).fetchone()
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    assert columns["model_version_id"][3] == 0
    assert columns["imported_model_id"][3] == 0
    assert row == ("run-1", "model-1", None, "completed")
    assert foreign_key_errors == []


def test_inference_source_constraint_requires_exactly_one_model_source(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    _legacy_database(database)
    migrate_imported_models(database)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO imported_models (id,name,task_type,format,original_name,artifact_path,size_bytes,sha256,status,class_names_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("import-1", "external", "segment", "pt", "external.pt", "/data/external.pt", 10, "a" * 64, "ready", "[]", "2026-07-20", "2026-07-20"),
        )
        connection.execute(
            "INSERT INTO inference_runs (id,model_version_id,imported_model_id,mode,runtime,config_json,status,progress,message,updated_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("run-2", None, "import-1", "image", "pt", "{}", "queued", 0, "Queued", "2026-07-20", "2026-07-20"),
        )
        with __import__("pytest").raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO inference_runs (id,model_version_id,imported_model_id,mode,runtime,config_json,status,progress,message,updated_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("invalid", None, None, "image", "pt", "{}", "queued", 0, "Queued", "2026-07-20", "2026-07-20"),
            )
