from pathlib import Path

import yaml
from typer.testing import CliRunner

from yolo_factory.cli.app import app


runner = CliRunner()


def test_help_lists_phase_one_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in (
        "init-storage",
        "video-import",
        "video-inspect",
        "frame-extract",
        "frame-deduplicate",
        "selection-sync",
        "annotation-package",
        "annotation-import",
        "dataset-check",
        "dataset-release",
    ):
        assert command in result.stdout


def test_init_storage_creates_standard_directories(tmp_path: Path) -> None:
    config = tmp_path / "system.yaml"
    storage = tmp_path / "storage"
    config.write_text(
        yaml.safe_dump({"storage_root": storage.as_posix()}),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["init-storage", "--system", str(config)])
    assert result.exit_code == 0, result.stdout
    for name in ("raw-videos", "frame-batches", "annotation-exports", "dataset-releases", "registry"):
        assert (storage / name).is_dir()
    assert (storage / "registry" / "factory.db").exists()
    assert (storage / ".dvc" / "config").exists()
