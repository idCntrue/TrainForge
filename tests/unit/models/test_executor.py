import subprocess
from pathlib import Path

import pytest

from yolo_factory.models import executor as executor_module
from yolo_factory.models.executor import LocalModelGateExecutor, ModelGateError


def test_model_gate_timeout_terminates_the_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class HungProcess:
        returncode = None
        terminated = False
        killed = False

        def wait(self, timeout=None):
            if not self.terminated:
                raise subprocess.TimeoutExpired("gate", timeout)
            self.returncode = -15
            return self.returncode

        def terminate(self):
            self.terminated = True

        def kill(self):
            self.killed = True
            self.returncode = -9

    process = HungProcess()
    monkeypatch.setattr(executor_module.subprocess, "Popen", lambda *args, **kwargs: process)
    executor = LocalModelGateExecutor(tmp_path, timeout_seconds=0.01)

    with pytest.raises(ModelGateError, match="timed out"):
        executor.run("model-001", {"model_id": "model-001"})

    assert process.terminated is True
