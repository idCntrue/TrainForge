import json
import os
import subprocess
import time
from pathlib import Path

import pytest

from yolo_factory.training import executor as executor_module
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, DatasetRelease, Task
from yolo_factory.training.executor import ActiveTrainingRunError, LocalTrainingExecutor
from yolo_factory.training.manifest import write_manifest
from yolo_factory.training.models import TrainingRunSpec
from yolo_factory.training.repository import TrainingRunRepository
from yolo_factory.training.resource_policy import InsufficientTrainingMemory, TrainingResourcePolicy


def _repository(path: Path) -> TrainingRunRepository:
    registry = create_registry(path)
    with session_scope(registry) as session:
        session.add(Task(id="lights", task_type="detect", annotation_format="yolo-detect", classes_json='["light"]'))
    with session_scope(registry) as session:
        session.add(AnnotationExport(id="annotation-lights-rf-1", task_id="lights", provider_project="lights", provider_version="1", zip_path="annotations.zip", sha256="a" * 64))
    with session_scope(registry) as session:
        session.add(DatasetRelease(id="dataset-lights-1.0.0", task_id="lights", annotation_export_id="annotation-lights-rf-1", version="1.0.0", release_path="datasets/lights/1.0.0", status="published"))
    return TrainingRunRepository(registry)


def _spec() -> TrainingRunSpec:
    return TrainingRunSpec("baseline", "detect", "dataset-lights-1.0.0", "yolo11n.pt", 5, 2, 640, "cuda:0")


def _wait_terminal(executor: LocalTrainingExecutor, run_id: str) -> str:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        run = executor.refresh(run_id)
        if run.status in {"completed", "failed", "cancelled", "interrupted"}:
            return run.status
        time.sleep(0.02)
    raise AssertionError("training run did not finish")


def test_manifest_is_immutable(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    release = tmp_path / "dataset-v1.0.0"
    release.mkdir()
    data_yaml = release / "data.yaml"
    data_yaml.write_text("path: .\n", encoding="utf-8")
    write_manifest(path, "run-001", _spec(), engine="ultralytics", dataset_release_path=release, data_yaml_path=data_yaml)

    with pytest.raises(FileExistsError):
        write_manifest(path, "run-001", _spec(), engine="ultralytics", dataset_release_path=release, data_yaml_path=data_yaml)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-001"
    assert payload["engine"] == "ultralytics"
    assert payload["dataset"]["data_yaml_path"] == str(data_yaml.resolve())


def test_start_persists_execution_policy_and_isolates_thread_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path / "factory.db")
    cpu_spec = TrainingRunSpec("cpu", "detect", "dataset-lights-1.0.0", "yolo11n.pt", 5, 2, 320, "cpu")
    repository.create(cpu_spec, run_id="run-cpu")
    captured: dict = {}
    call_order: list[str] = []

    class FakeProcess:
        pid = 12345

        def poll(self):
            return None

    def fake_popen(*args, **kwargs):
        call_order.append("popen")
        captured.update(kwargs)
        return FakeProcess()

    monkeypatch.setattr(executor_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        executor_module,
        "read_training_memory_snapshot",
        lambda: call_order.append("snapshot") or {"cgroup_memory_oom_kill": 0},
    )
    before = dict(os.environ)
    executor = LocalTrainingExecutor(
        repository,
        tmp_path / "storage",
        resource_policy=TrainingResourcePolicy.from_environment({"CPU_TRAINING_THREADS": "3"}),
    )

    executor.start("run-cpu")

    manifest = json.loads((tmp_path / "storage" / "training-runs" / "run-cpu" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["execution"] == {"workers": 0, "cache": False, "cpu_threads": 3}
    assert {name: captured["env"][name] for name in (
        "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"
    )} == {
        "OMP_NUM_THREADS": "3",
        "MKL_NUM_THREADS": "3",
        "OPENBLAS_NUM_THREADS": "3",
        "NUMEXPR_NUM_THREADS": "3",
    }
    assert dict(os.environ) == before
    assert call_order[:2] == ["snapshot", "popen"]


def test_start_rejects_low_windows_memory_before_creating_run_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-low-memory")
    storage = tmp_path / "storage"
    popen_called = False

    def fail_popen(*args, **kwargs):
        nonlocal popen_called
        popen_called = True
        raise AssertionError("runner must not start")

    monkeypatch.setattr(executor_module.subprocess, "Popen", fail_popen)
    monkeypatch.setattr(executor_module, "read_training_memory_snapshot", lambda: {
        "windows_available_commit_bytes": 2 * 1024**3,
        "windows_available_physical_bytes": 6 * 1024**3,
        "windows_leaspac_process_count": 12,
        "windows_leaspac_private_bytes": 10 * 1024**3,
    })
    executor = LocalTrainingExecutor(repository, storage)

    with pytest.raises(InsufficientTrainingMemory):
        executor.start("run-low-memory")

    assert popen_called is False
    assert not (storage / "training-runs" / "run-low-memory").exists()
    assert repository.get_required("run-low-memory").status == "queued"


def test_simulated_subprocess_completes_release_gates(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-001")
    executor = LocalTrainingExecutor(repository, tmp_path / "storage", engine="simulation", simulation_step_seconds=0.01)

    started = executor.start("run-001")

    assert started.status == "running"
    assert _wait_terminal(executor, "run-001") == "completed"
    assert (tmp_path / "storage" / "training-runs" / "run-001" / "progress.jsonl").exists()


def test_rejects_second_active_run(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-001")
    repository.create(_spec(), run_id="run-002")
    executor = LocalTrainingExecutor(repository, tmp_path / "storage", engine="simulation", simulation_step_seconds=0.2)
    executor.start("run-001")

    with pytest.raises(ActiveTrainingRunError):
        executor.start("run-002")

    executor.cancel("run-001")


def test_cancels_running_subprocess(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-001")
    executor = LocalTrainingExecutor(repository, tmp_path / "storage", engine="simulation", simulation_step_seconds=0.2)
    executor.start("run-001")

    cancelled = executor.cancel("run-001")

    assert cancelled.status == "cancelled"


def test_cancels_runner_started_before_executor_restart(tmp_path: Path) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-001")
    original_executor = LocalTrainingExecutor(repository, tmp_path / "storage", engine="simulation", simulation_step_seconds=0.5)
    started = original_executor.start("run-001")
    restarted_executor = LocalTrainingExecutor(repository, tmp_path / "storage", engine="simulation", simulation_step_seconds=0.5)

    cancelled = restarted_executor.cancel("run-001")

    assert cancelled.status == "cancelled"
    assert started.pid is not None
    assert original_executor._processes["run-001"].wait(timeout=1) is not None


def test_process_exists_handles_windows_system_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def failed_kill(pid: int, signal: int) -> None:
        raise SystemError("Windows process lookup failed")

    monkeypatch.setattr(executor_module.os, "kill", failed_kill)

    assert executor_module._process_exists(999_999) is False


def test_refresh_interrupts_restarted_run_after_persisted_process_disappears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-orphaned")
    run_directory = tmp_path / "storage" / "training-runs" / "run-orphaned"
    run_directory.mkdir(parents=True)
    repository.transition(
        "run-orphaned",
        "running",
        phase="training",
        pid=987_654,
        run_directory=str(run_directory),
    )
    monkeypatch.setattr(executor_module, "_process_exists", lambda pid: False)
    restarted_executor = LocalTrainingExecutor(repository, tmp_path / "storage")

    refreshed = restarted_executor.refresh("run-orphaned")

    assert refreshed.status == "interrupted"
    assert refreshed.message == "Runner process is no longer available"


def test_windows_process_tree_termination_uses_taskkill(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(executor_module.subprocess, "run", fake_run)

    executor_module._terminate_process_tree(1234, platform_name="nt")

    assert calls[0][0] == ["taskkill", "/PID", "1234", "/T", "/F"]
    assert calls[0][1]["check"] is False


def test_posix_process_tree_termination_kills_process_group(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(executor_module.os, "killpg", lambda pid, sig: calls.append((pid, sig)), raising=False)

    executor_module._terminate_process_tree(1234, platform_name="posix")

    assert calls == [(1234, executor_module.signal.SIGTERM)]


@pytest.mark.parametrize("return_code", [-9, 137])
def test_marks_resource_killed_process_with_actionable_failure(
    tmp_path: Path, return_code: int, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _repository(tmp_path / "factory.db")
    repository.create(_spec(), run_id="run-killed")
    run_directory = tmp_path / "storage" / "training-runs" / "run-killed"
    weights = run_directory / "ultralytics" / "weights"
    weights.mkdir(parents=True)
    (weights / "best.pt").write_bytes(b"valid-weight-evidence")
    (run_directory / "progress.jsonl").write_text(json.dumps({
        "status": "running", "phase": "training", "progress": 78,
        "message": "Epoch 78", "epoch": 78, "total_epochs": 100,
    }) + "\n", encoding="utf-8")
    repository.transition(
        "run-killed", "running", phase="training", pid=123,
        run_directory=str(run_directory),
    )
    monkeypatch.setenv("API_MEMORY_LIMIT", "10g")
    executor = LocalTrainingExecutor(repository, tmp_path / "storage")

    class KilledProcess:
        returncode = return_code

        def poll(self):
            return return_code

    executor._processes["run-killed"] = KilledProcess()
    original_transition = repository.transition

    def transition_after_diagnostic(run_id, status, **kwargs):
        if status == "failed":
            assert (run_directory / "failure.json").is_file()
        return original_transition(run_id, status, **kwargs)

    repository.transition = transition_after_diagnostic

    failed = executor.refresh("run-killed")
    diagnostic = json.loads((run_directory / "failure.json").read_text(encoding="utf-8"))

    assert failed.status == "failed"
    assert failed.exit_code == return_code
    assert diagnostic["code"] == "resource_limit"
    assert diagnostic["last_successful_epoch"] == 78
    assert diagnostic["recoverability"]["can_safe_retry"] is True
    assert diagnostic["recoverability"]["can_evaluate_best"] is False
    assert diagnostic["resource_snapshot"]["configured_memory_limit_bytes"] == 10737418240
