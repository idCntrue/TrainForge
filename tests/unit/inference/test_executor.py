import json
from pathlib import Path

from yolo_factory.inference.executor import LocalInferenceExecutor
from yolo_factory.inference.repository import InferenceRunRepository
from tests.unit.inference.test_repository import _repository


class FakeProcess:
    pid = 4321

    def __init__(self) -> None:
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def wait(self, timeout=None):
        del timeout
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def test_starts_refreshes_and_cancels_background_inference(tmp_path: Path, monkeypatch) -> None:
    repository: InferenceRunRepository = _repository(tmp_path / "factory.db")
    repository.create(run_id="inference-001", model_version_id="model-001", mode="image", runtime="pt", sources=["input.jpg"], confidence=0.25)
    process = FakeProcess()
    monkeypatch.setattr("yolo_factory.inference.executor.subprocess.Popen", lambda *args, **kwargs: process)
    executor = LocalInferenceExecutor(repository, tmp_path)

    started = executor.start("inference-001", {"mode": "image", "sources": ["input.jpg"]})
    run_directory = Path(started["run_directory"])
    result_path = run_directory / "result.json"
    result_path.write_text(json.dumps({"items": [], "media": []}), encoding="utf-8")
    (run_directory / "progress.jsonl").write_text(json.dumps({"status": "completed", "progress": 100, "message": "Completed"}) + "\n", encoding="utf-8")
    process.returncode = 0
    completed = executor.refresh("inference-001")

    repository.create(run_id="inference-002", model_version_id="model-001", mode="image", runtime="pt", sources=["input.jpg"], confidence=0.25)
    process.returncode = None
    executor.start("inference-002", {"mode": "image", "sources": ["input.jpg"]})
    cancelled = executor.cancel("inference-002")

    assert started["status"] == "running"
    assert completed["status"] == "completed"
    assert completed["result_path"] == str(result_path)
    assert cancelled["status"] == "cancelled"
