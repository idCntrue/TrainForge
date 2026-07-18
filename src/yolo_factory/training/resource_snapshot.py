from __future__ import annotations

from pathlib import Path


def _read_integer(path: Path) -> int | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
        return None if raw == "max" else int(raw)
    except (OSError, ValueError):
        return None


def read_cgroup_memory_snapshot(cgroup_root: str | Path = "/sys/fs/cgroup") -> dict[str, int | None]:
    root = Path(cgroup_root)
    events: dict[str, int] = {}
    try:
        for line in (root / "memory.events").read_text(encoding="utf-8").splitlines():
            key, value = line.split(maxsplit=1)
            events[key] = int(value)
    except (OSError, ValueError):
        pass
    return {
        "cgroup_memory_limit_bytes": _read_integer(root / "memory.max"),
        "cgroup_memory_current_bytes": _read_integer(root / "memory.current"),
        "cgroup_memory_peak_bytes": _read_integer(root / "memory.peak"),
        "cgroup_memory_oom": events.get("oom"),
        "cgroup_memory_oom_kill": events.get("oom_kill"),
    }
