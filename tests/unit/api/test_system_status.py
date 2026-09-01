from pathlib import Path

from yolo_factory.api.system_status import _probe_environment, system_status
from yolo_factory.registry.database import create_registry


def test_system_status_returns_full_structure(tmp_path: Path) -> None:
    database_path = tmp_path / "registry" / "factory.db"
    registry = create_registry(database_path)

    payload = system_status(registry, tmp_path, database_path)

    assert payload["status"] == "ok"
    assert payload["storage_root"] == str(tmp_path)
    assert set(payload["disk"]) == {"total", "used", "free"}
    assert payload["disk"]["free"] >= 0
    assert set(payload["gpu"]) == {"available", "device", "memory_bytes", "cuda_version"}
    assert isinstance(payload["gpu"]["available"], bool)
    assert set(payload["versions"]) == {"python", "torch", "ultralytics", "cuda"}
    assert payload["versions"]["python"]
    assert payload["active_jobs"] == {"training": 0, "inference": 0}
    assert payload["database"]["path"] == str(database_path)
    assert payload["database"]["size_bytes"] == database_path.stat().st_size


def test_environment_probe_is_cached() -> None:
    assert _probe_environment() == _probe_environment()
