from pathlib import Path

from sqlalchemy import create_engine, text


def migrate_model_versions(database: Path) -> None:
    """Remove the legacy one-model-per-training unique constraint safely."""
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        indexes = list(connection.execute(text("PRAGMA index_list(model_versions)")))
        has_legacy_unique = False
        for row in indexes:
            if not bool(row[2]):
                continue
            columns = [str(item[2]) for item in connection.execute(text(f"PRAGMA index_info('{row[1]}')"))]
            if columns == ["training_run_id"]:
                has_legacy_unique = True
                break
        if not has_legacy_unique:
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_model_versions_training_run_id ON model_versions(training_run_id)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_model_versions_name_version ON model_versions(name, version)"))
            return
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("""
            CREATE TABLE model_versions_new (
                id VARCHAR(160) NOT NULL PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                version VARCHAR(64) NOT NULL,
                task_type VARCHAR(16) NOT NULL,
                training_run_id VARCHAR(160) NOT NULL REFERENCES training_runs(id) ON DELETE RESTRICT,
                dataset_release_id VARCHAR(160) NOT NULL REFERENCES dataset_releases(id) ON DELETE RESTRICT,
                config_json TEXT NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'candidate',
                gates_json TEXT NOT NULL DEFAULT '{}',
                gate_report_path TEXT,
                published_at DATETIME,
                archived_at DATETIME,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
        """))
        connection.execute(text("""
            INSERT INTO model_versions_new
            SELECT id, name, version, task_type, training_run_id, dataset_release_id,
                   config_json, status, gates_json, gate_report_path, published_at,
                   archived_at, created_at, updated_at
            FROM model_versions
        """))
        connection.execute(text("DROP TABLE model_versions"))
        connection.execute(text("ALTER TABLE model_versions_new RENAME TO model_versions"))
        connection.execute(text("CREATE INDEX ix_model_versions_task_type ON model_versions(task_type)"))
        connection.execute(text("CREATE INDEX ix_model_versions_status ON model_versions(status)"))
        connection.execute(text("CREATE INDEX ix_model_versions_training_run_id ON model_versions(training_run_id)"))
        connection.execute(text("CREATE UNIQUE INDEX uq_model_versions_name_version ON model_versions(name, version)"))
        connection.execute(text("PRAGMA foreign_keys=ON"))
        violations = list(connection.execute(text("PRAGMA foreign_key_check")))
        if violations:
            raise RuntimeError(f"model_versions migration introduced foreign key violations: {violations[:3]}")
