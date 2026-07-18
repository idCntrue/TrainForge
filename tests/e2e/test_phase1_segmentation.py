from pathlib import Path

from tests.e2e.workflow_support import run_phase_one


def test_phase_one_segmentation_workflow(tmp_path: Path) -> None:
    release = run_phase_one(tmp_path, "segment")
    row = (release / "test" / "labels" / "sample-test.txt").read_text(
        encoding="utf-8"
    )
    assert len(row.split()) == 9
