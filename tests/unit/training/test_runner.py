import json
from pathlib import Path

from yolo_factory.training import runner
from yolo_factory.training import ultralytics_adapter


def test_runner_persists_traceback_phase_and_last_successful_epoch(
    tmp_path: Path, monkeypatch,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"run_id": "run-failed", "engine": "ultralytics"}),
        encoding="utf-8",
    )

    def fail_after_epoch(manifest, run_directory, emit):
        del manifest, run_directory
        emit({
            "status": "running",
            "phase": "training",
            "progress": 79.0,
            "message": "Epoch 79 completed",
            "epoch": 79,
            "total_epochs": 100,
        })
        raise RuntimeError("deterministic training failure")

    monkeypatch.setattr(ultralytics_adapter, "run_ultralytics", fail_after_epoch)

    assert runner.run(manifest_path) == 1
    events = [json.loads(line) for line in (tmp_path / "progress.jsonl").read_text(encoding="utf-8").splitlines()]
    failed = events[-1]

    assert failed["status"] == "failed"
    assert failed["phase"] == "training"
    assert failed["last_successful_epoch"] == 79
    assert failed["total_epochs"] == 100
    assert failed["exception_type"] == "RuntimeError"
    assert failed["technical_message"] == "deterministic training failure"
    assert "raise RuntimeError(\"deterministic training failure\")" in failed["traceback"]
