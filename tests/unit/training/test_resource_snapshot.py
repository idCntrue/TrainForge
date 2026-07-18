from pathlib import Path

from yolo_factory.training.resource_snapshot import read_cgroup_memory_snapshot


def test_reads_cgroup_v2_memory_snapshot(tmp_path: Path) -> None:
    (tmp_path / "memory.max").write_text("10737418240\n", encoding="utf-8")
    (tmp_path / "memory.current").write_text("2147483648\n", encoding="utf-8")
    (tmp_path / "memory.peak").write_text("8589934592\n", encoding="utf-8")
    (tmp_path / "memory.events").write_text(
        "low 0\nhigh 0\nmax 12\noom 2\noom_kill 1\n",
        encoding="utf-8",
    )

    assert read_cgroup_memory_snapshot(tmp_path) == {
        "cgroup_memory_limit_bytes": 10737418240,
        "cgroup_memory_current_bytes": 2147483648,
        "cgroup_memory_peak_bytes": 8589934592,
        "cgroup_memory_oom": 2,
        "cgroup_memory_oom_kill": 1,
    }


def test_tolerates_unlimited_or_missing_cgroup_files(tmp_path: Path) -> None:
    (tmp_path / "memory.max").write_text("max\n", encoding="utf-8")

    snapshot = read_cgroup_memory_snapshot(tmp_path)

    assert snapshot["cgroup_memory_limit_bytes"] is None
    assert snapshot["cgroup_memory_current_bytes"] is None
