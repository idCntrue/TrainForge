import json
import os
from pathlib import Path

import pytest

from yolo_factory.models.gate_history import gate_run_directory, list_gate_runs


def _attempt(root: Path, model_id: str, run_id: str, *, result: dict | None = None) -> Path:
    directory = root / "model-versions" / model_id / "gate-runs" / run_id
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps({"model_id": model_id}), encoding="utf-8")
    (directory / "runner.log").write_text("gate log", encoding="utf-8")
    if result is not None:
        exported = directory / "exported" / "source.onnx"
        exported.parent.mkdir()
        exported.write_bytes(b"onnx-data")
        result = {
            **result,
            "artifacts": {"onnx": {"path": str(exported), "size_bytes": exported.stat().st_size}},
        }
        (directory / "result.json").write_text(json.dumps(result), encoding="utf-8")
    return directory


def test_lists_gate_runs_newest_first_with_status_size_and_active_marker(tmp_path: Path) -> None:
    older = _attempt(tmp_path, "model-1", "run-old", result={
        "passed": False,
        "gates": {"consistency": False, "mask_consistency": False},
        "samples": [],
    })
    newer = _attempt(tmp_path, "model-1", "run-new", result={
        "passed": True,
        "gates": {"consistency": True, "mask_consistency": False},
        "samples": [{"passed": True, "mask_consistency": False}],
    })
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    runs = list_gate_runs(tmp_path, "model-1", active_report_path=newer / "result.json")

    assert [run["id"] for run in runs] == ["run-new", "run-old"]
    assert runs[0]["active"] is True
    assert runs[0]["status"] == "completed_with_warnings"
    assert runs[0]["gates"]["consistency"] is True
    assert runs[0]["onnx"]["exists"] is True
    assert runs[0]["total_size_bytes"] > runs[0]["onnx"]["size_bytes"]
    assert runs[0]["diagnostics_available"] is True
    assert runs[1]["status"] == "blocked"


def test_lists_incomplete_attempt_without_breaking_history(tmp_path: Path) -> None:
    attempt = _attempt(tmp_path, "model-1", "run-incomplete")

    runs = list_gate_runs(tmp_path, "model-1", active_report_path=None)

    assert len(runs) == 1
    assert runs[0]["id"] == "run-incomplete"
    assert runs[0]["status"] == "incomplete"
    assert runs[0]["active"] is False
    assert runs[0]["onnx"] is None
    assert runs[0]["diagnostics_available"] is False


@pytest.mark.parametrize("run_id", ["../other", "a/b", "a\\b", "", ".", ".."])
def test_rejects_unsafe_gate_run_ids(tmp_path: Path, run_id: str) -> None:
    with pytest.raises(ValueError, match="invalid gate run id"):
        gate_run_directory(tmp_path, "model-1", run_id)


def test_rejects_symlinked_gate_run_directory(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "model-versions" / "model-1" / "gate-runs"
    root.mkdir(parents=True)
    link = root / "linked-run"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable")

    assert list_gate_runs(tmp_path, "model-1", active_report_path=None) == []
