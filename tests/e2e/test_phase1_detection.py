from pathlib import Path

from tests.e2e.workflow_support import run_phase_one


def test_phase_one_detection_workflow(tmp_path: Path) -> None:
    release = run_phase_one(tmp_path, "detect")
    assert (release / "train" / "labels" / "sample-train.txt").exists()
