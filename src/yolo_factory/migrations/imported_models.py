from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportedModelsMigrationReport:
    rebuilt_inference_runs: bool
    preserved_rows: int


_IMPORTED_MODELS_SQL = """
CREATE TABLE IF NOT EXISTS imported_models (
    id VARCHAR(160) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    task_type VARCHAR(16) NOT NULL,
    format VARCHAR(16) NOT NULL,
    original_name TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    class_names_json TEXT NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""


def migrate_imported_models(database: Path) -> ImportedModelsMigrationReport:
    if not database.is_file():
        return ImportedModelsMigrationReport(False, 0)
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(_IMPORTED_MODELS_SQL)
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='inference_runs'"
        ).fetchone()
        if table is None:
            connection.commit()
            return ImportedModelsMigrationReport(False, 0)
        columns = {str(row[1]): row for row in connection.execute("PRAGMA table_info(inference_runs)")}
        if "imported_model_id" in columns and columns["model_version_id"][3] == 0:
            rows = connection.execute("SELECT COUNT(*) FROM inference_runs").fetchone()[0]
            connection.commit()
            return ImportedModelsMigrationReport(False, int(rows))

        rows_before = int(connection.execute("SELECT COUNT(*) FROM inference_runs").fetchone()[0])
        connection.execute("""
            CREATE TABLE inference_runs_new (
                id VARCHAR(160) PRIMARY KEY,
                model_version_id VARCHAR(160) REFERENCES model_versions(id) ON DELETE RESTRICT,
                imported_model_id VARCHAR(160) REFERENCES imported_models(id) ON DELETE RESTRICT,
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
                created_at DATETIME NOT NULL,
                CONSTRAINT ck_inference_runs_single_model_source CHECK (
                    (model_version_id IS NOT NULL AND imported_model_id IS NULL) OR
                    (model_version_id IS NULL AND imported_model_id IS NOT NULL)
                )
            )
        """)
        connection.execute("""
            INSERT INTO inference_runs_new (
                id, model_version_id, imported_model_id, mode, runtime, config_json,
                status, progress, message, output_directory, result_path, finished_at,
                updated_at, created_at
            )
            SELECT id, model_version_id, NULL, mode, runtime, config_json,
                status, progress, message, output_directory, result_path, finished_at,
                updated_at, created_at
            FROM inference_runs
        """)
        rows_after = int(connection.execute("SELECT COUNT(*) FROM inference_runs_new").fetchone()[0])
        if rows_after != rows_before:
            raise RuntimeError("inference migration row count mismatch")
        connection.execute("DROP TABLE inference_runs")
        connection.execute("ALTER TABLE inference_runs_new RENAME TO inference_runs")
        connection.execute("CREATE INDEX ix_inference_runs_model_version_id ON inference_runs(model_version_id)")
        connection.execute("CREATE INDEX ix_inference_runs_imported_model_id ON inference_runs(imported_model_id)")
        connection.execute("CREATE INDEX ix_inference_runs_status ON inference_runs(status)")
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError("inference migration introduced foreign key violations")
        connection.commit()
        return ImportedModelsMigrationReport(True, rows_after)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
