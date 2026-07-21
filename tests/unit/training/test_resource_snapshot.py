from pathlib import Path

from yolo_factory.training.resource_snapshot import (
    build_windows_memory_snapshot,
    read_cgroup_memory_snapshot,
    read_training_memory_snapshot,
)


GIB = 1024**3


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


def test_builds_windows_memory_snapshot_with_leaspac_evidence() -> None:
    snapshot = build_windows_memory_snapshot(
        total_physical=16 * GIB,
        available_physical=5 * GIB,
        commit_limit=64 * GIB,
        available_commit=6 * GIB,
        processes=[
            ("LeASPac.exe", 11, 2 * GIB),
            ("python.exe", 22, 4 * GIB),
            ("leaspac.EXE", 33, 3 * GIB),
        ],
    )

    assert snapshot["windows_total_physical_bytes"] == 16 * GIB
    assert snapshot["windows_available_physical_bytes"] == 5 * GIB
    assert snapshot["windows_commit_limit_bytes"] == 64 * GIB
    assert snapshot["windows_committed_bytes"] == 58 * GIB
    assert snapshot["windows_available_commit_bytes"] == 6 * GIB
    assert snapshot["windows_leaspac_process_count"] == 2
    assert snapshot["windows_leaspac_private_bytes"] == 5 * GIB
    assert snapshot["windows_largest_process_private_bytes"] == 4 * GIB


def test_training_snapshot_keeps_linux_cgroup_behavior(tmp_path: Path) -> None:
    (tmp_path / "memory.max").write_text("10737418240\n", encoding="utf-8")

    snapshot = read_training_memory_snapshot(platform_name="posix", cgroup_root=tmp_path)

    assert snapshot["cgroup_memory_limit_bytes"] == 10737418240
    assert "windows_available_commit_bytes" not in snapshot
