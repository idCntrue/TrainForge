import json
import subprocess
from pathlib import Path

import pytest

from yolo_factory.operations.acceptance import UnsafeAcceptanceRoot, run_acceptance


def test_acceptance_refuses_nonempty_root(tmp_path: Path) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "factory.db").write_bytes(b"business")

    with pytest.raises(UnsafeAcceptanceRoot, match="empty"):
        run_acceptance(occupied, duration_seconds=0.05, sample_interval_seconds=0.01)

    assert (occupied / "factory.db").read_bytes() == b"business"


def test_acceptance_refuses_configured_production_root(tmp_path: Path, monkeypatch) -> None:
    production = tmp_path / "production"
    monkeypatch.setenv("YOLO_FACTORY_STORAGE_ROOT", str(production))

    with pytest.raises(UnsafeAcceptanceRoot, match="production"):
        run_acceptance(production, duration_seconds=0.05, sample_interval_seconds=0.01)

    assert not production.exists()


def test_short_acceptance_writes_complete_json_and_markdown_reports(tmp_path: Path) -> None:
    root = tmp_path / "new-acceptance-root"

    result = run_acceptance(root, duration_seconds=0.05, sample_interval_seconds=0.01)

    assert result.passed is True
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["checks"] == {
        "registry_round_trip": "passed",
        "background_job_recovery": "passed",
        "heavy_lease_reclaim": "passed",
        "simulated_training_lifecycle": "passed",
        "simulated_inference_lifecycle": "passed",
        "database_backup": "passed",
        "resource_growth": "passed",
    }
    assert payload["samples"] >= 2
    assert result.markdown_path.is_file()
    assert "# TrainForge Stability Acceptance" in result.markdown_path.read_text(encoding="utf-8")


def test_powershell_wrapper_runs_short_acceptance_in_selected_root(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[3]
    root = tmp_path / "wrapper-acceptance"

    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(project_root / "scripts" / "run-stability-acceptance.ps1"),
            "-Mode",
            "short",
            "-Root",
            str(root),
            "-DurationSeconds",
            "0.05",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert (root / "acceptance-report.json").is_file()
