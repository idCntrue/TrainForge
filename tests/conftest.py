import pytest


@pytest.fixture(autouse=True)
def deterministic_training_disk_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRAINING_MIN_FREE_DISK_GB", "1")
    monkeypatch.setenv("TRAINING_MIN_FREE_DISK_PERCENT", "1")
