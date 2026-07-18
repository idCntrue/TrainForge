import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from yolo_factory.cli.app import app
from yolo_factory.migrations.storage_paths import (
    convert_json_paths,
    convert_storage_path,
    migrate_storage_paths,
)


def test_converts_windows_storage_paths_case_insensitively() -> None:
    assert convert_storage_path(
        r"D:\YOLO_DATA\training-runs\run-1",
        r"D:\YOLO_DATA",
        Path("/data"),
    ).value == "/data/training-runs/run-1"
    assert convert_storage_path(
        "d:/yolo_data/model-versions/model-1/best.pt",
        r"D:\YOLO_DATA",
        Path("/data"),
    ).value == "/data/model-versions/model-1/best.pt"


def test_converts_storage_root_itself() -> None:
    result = convert_storage_path(r"D:\YOLO_DATA", r"D:\YOLO_DATA", Path("/data"))
    assert result.value == "/data"
    assert result.status == "converted"


def test_reports_external_absolute_paths_without_changing_them() -> None:
    result = convert_storage_path(r"D:\videoTmp\input.jpg", r"D:\YOLO_DATA", Path("/data"))
    assert result.value == r"D:\videoTmp\input.jpg"
    assert result.status == "external"


def test_leaves_relative_and_already_migrated_paths_unchanged() -> None:
    assert convert_storage_path("raw-videos/task/video.mp4", r"D:\YOLO_DATA", Path("/data")).status == "unchanged"
    assert convert_storage_path("/data/training-runs/run-1", r"D:\YOLO_DATA", Path("/data")).status == "unchanged"


def test_recursively_converts_json_paths_and_collects_external_paths() -> None:
    result = convert_json_paths({
        "artifact": {"path": r"D:\YOLO_DATA\models\best.pt"},
        "sources": [r"D:\videoTmp\input.jpg", "relative.jpg"],
    }, r"D:\YOLO_DATA", Path("/data"))

    assert result.value["artifact"]["path"] == "/data/models/best.pt"
    assert result.value["sources"][0] == r"D:\videoTmp\input.jpg"
    assert result.converted == 1
    assert result.external_paths == (r"D:\videoTmp\input.jpg",)


def _database(path: Path, *, invalid_json: bool = False) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE frame_assets (stored_path TEXT NOT NULL);
        CREATE TABLE annotation_images (image_path TEXT NOT NULL);
        CREATE TABLE training_runs (base_model TEXT NOT NULL, config_json TEXT NOT NULL, run_directory TEXT);
        CREATE TABLE model_versions (config_json TEXT NOT NULL, gate_report_path TEXT);
        CREATE TABLE inference_runs (config_json TEXT NOT NULL, output_directory TEXT, result_path TEXT);
    """)
    connection.execute("INSERT INTO frame_assets VALUES (?)", (r"D:\YOLO_DATA\frames\one.jpg",))
    connection.execute("INSERT INTO annotation_images VALUES (?)", (r"D:\YOLO_DATA\frames\one.jpg",))
    training_config = "{invalid" if invalid_json else json.dumps({"data_yaml": r"D:\YOLO_DATA\datasets\one\data.yaml"})
    connection.execute(
        "INSERT INTO training_runs VALUES (?, ?, ?)",
        ("yolo11n.pt", training_config, r"D:\YOLO_DATA\training-runs\run-1"),
    )
    connection.execute(
        "INSERT INTO model_versions VALUES (?, ?)",
        (json.dumps({"pt_path": r"D:\YOLO_DATA\models\best.pt"}), r"D:\YOLO_DATA\models\gate.json"),
    )
    connection.execute(
        "INSERT INTO inference_runs VALUES (?, ?, ?)",
        (
            json.dumps({"sources": [r"D:\videoTmp\input.jpg"], "run_directory": r"D:\YOLO_DATA\inference-runs\run-1"}),
            r"D:\YOLO_DATA\inference-runs\run-1",
            r"D:\YOLO_DATA\inference-runs\run-1\missing.json",
        ),
    )
    connection.commit()
    connection.close()


def test_database_migration_dry_run_apply_backup_and_idempotency(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    new_root = tmp_path / "data"
    (new_root / "frames").mkdir(parents=True)
    (new_root / "frames" / "one.jpg").write_bytes(b"image")
    (new_root / "datasets" / "one").mkdir(parents=True)
    (new_root / "datasets" / "one" / "data.yaml").write_text("path: .", encoding="utf-8")
    (new_root / "training-runs" / "run-1").mkdir(parents=True)
    (new_root / "models").mkdir(parents=True)
    (new_root / "models" / "best.pt").write_bytes(b"weights")
    (new_root / "models" / "gate.json").write_text("{}", encoding="utf-8")
    (new_root / "inference-runs" / "run-1").mkdir(parents=True)
    _database(database)

    dry_run = migrate_storage_paths(database, r"D:\YOLO_DATA", new_root, apply=False)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT stored_path FROM frame_assets").fetchone()[0].startswith("D:")
    assert dry_run.updated_values >= 8
    assert dry_run.backup_path is None
    assert dry_run.external_paths == (r"D:\videoTmp\input.jpg",)
    assert any(path.endswith("missing.json") for path in dry_run.missing_paths)

    applied = migrate_storage_paths(database, r"D:\YOLO_DATA", new_root, apply=True)
    assert applied.backup_path is not None
    assert Path(applied.backup_path).is_file()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT stored_path FROM frame_assets").fetchone()[0] == (new_root / "frames" / "one.jpg").as_posix()
        config = json.loads(connection.execute("SELECT config_json FROM model_versions").fetchone()[0])
        assert config["pt_path"] == (new_root / "models" / "best.pt").as_posix()

    repeated = migrate_storage_paths(database, r"D:\YOLO_DATA", new_root, apply=False)
    assert repeated.updated_values == 0


def test_database_migration_does_not_partially_update_invalid_json(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    _database(database, invalid_json=True)

    with pytest.raises(ValueError, match="training_runs.config_json"):
        migrate_storage_paths(database, r"D:\YOLO_DATA", tmp_path / "data", apply=True)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT stored_path FROM frame_assets").fetchone()[0] == r"D:\YOLO_DATA\frames\one.jpg"


def test_migration_cli_defaults_to_dry_run_json_report(tmp_path: Path) -> None:
    database = tmp_path / "factory.db"
    _database(database)

    result = CliRunner().invoke(app, [
        "migrate-storage-paths",
        "--database", str(database),
        "--old-root", r"D:\YOLO_DATA",
        "--new-root", str(tmp_path / "data"),
    ])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["applied"] is False
    assert report["updated_values"] >= 8
