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


def test_refresh_fails_clean_exit_without_result_and_forgets_process(tmp_path: Path) -> None:
    repository: InferenceRunRepository = _repository(tmp_path / "factory.db")
    repository.create(
        run_id="inference-incomplete",
        model_version_id="model-001",
        mode="image",
        runtime="pt",
        sources=["input.jpg"],
        confidence=0.25,
    )
    executor = LocalInferenceExecutor(repository, tmp_path)
    process = FakeProcess()
    monkeypatch_process = process

    directory = tmp_path / "inference-runs" / "inference-incomplete"
    directory.mkdir(parents=True)
    repository.update(
        "inference-incomplete",
        "running",
        progress=10,
        message="Running",
        pid=process.pid,
        run_directory=str(directory),
    )
    process.returncode = 0
    executor._processes["inference-incomplete"] = monkeypatch_process

    refreshed = executor.refresh("inference-incomplete")

    assert refreshed["status"] == "failed"
    assert "without a completed result" in refreshed["message"]
    assert "inference-incomplete" not in executor._processes


def test_refresh_does_not_reapply_already_consumed_inference_event(tmp_path: Path) -> None:
    repository: InferenceRunRepository = _repository(tmp_path / "factory.db")
    repository.create(
        run_id="inference-incremental",
        model_version_id="model-001",
        mode="image",
        runtime="pt",
        sources=["input.jpg"],
        confidence=0.25,
    )
    directory = tmp_path / "inference-runs" / "inference-incremental"
    directory.mkdir(parents=True)
    (directory / "process.json").write_text('{"pid": 4321}', encoding="utf-8")
    (directory / "progress.jsonl").write_text(
        json.dumps({"status": "running", "progress": 20, "message": "Loaded"}) + "\n",
        encoding="utf-8",
    )
    repository.update(
        "inference-incremental",
        "running",
        progress=2,
        message="Started",
        pid=4321,
        run_directory=str(directory),
    )
    executor = LocalInferenceExecutor(repository, tmp_path)
    process = FakeProcess()
    executor._processes["inference-incremental"] = process
    updates = 0
    original_update = repository.update

    def counted_update(*args, **kwargs):
        nonlocal updates
        updates += 1
        return original_update(*args, **kwargs)

    repository.update = counted_update

    executor.refresh("inference-incremental")
    executor.refresh("inference-incremental")

    assert updates == 1
    metadata = json.loads((directory / "process.json").read_text(encoding="utf-8"))
    assert metadata["progress_offset"] == (directory / "progress.jsonl").stat().st_size
