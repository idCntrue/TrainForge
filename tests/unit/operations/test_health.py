from types import SimpleNamespace

from yolo_factory.operations.health import OperationalHealthCollector, _gpu_probe
from yolo_factory.registry.database import create_registry


def test_health_snapshot_keeps_partial_evidence_when_gpu_probe_fails(tmp_path) -> None:
    collector = OperationalHealthCollector(
        storage_root=tmp_path,
        registry=create_registry(tmp_path / "registry" / "factory.db"),
        process_memory=lambda: 1234,
        disk_usage=lambda _: SimpleNamespace(total=100, used=40, free=60),
        memory_snapshot=lambda: {"windows_available_commit_bytes": 90},
        gpu_probe=lambda: (_ for _ in ()).throw(TimeoutError("nvidia-smi timeout")),
        active_work=lambda: {"training": 1, "inference": 1, "background_jobs": 0, "heavy_operation": "model-gates"},
    )

    snapshot = collector.collect()

    assert snapshot["api_process_rss_bytes"] == 1234
    assert snapshot["storage"] == {"total_bytes": 100, "used_bytes": 40, "free_bytes": 60, "free_percent": 60.0}
    assert snapshot["gpu"] is None
    assert snapshot["sqlite"]["quick_check"] == "ok"
    assert snapshot["active_work"]["heavy_operation"] == "model-gates"
    assert snapshot["warnings"] == ["GPU metrics unavailable: nvidia-smi timeout"]


def test_gpu_probe_uses_configured_timeout(monkeypatch) -> None:
    observed = {}

    def run(*args, **kwargs):
        observed["timeout"] = kwargs["timeout"]
        return SimpleNamespace(stdout="NVIDIA GeForce RTX 4060, 8192, 1024, 25\n")

    monkeypatch.setenv("HEALTH_GPU_PROBE_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setattr("yolo_factory.operations.health.subprocess.run", run)

    assert _gpu_probe()["name"] == "NVIDIA GeForce RTX 4060"
    assert observed["timeout"] == 3.5
