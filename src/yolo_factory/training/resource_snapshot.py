from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Iterable


WindowsProcessReading = tuple[str, int, int]


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


def build_windows_memory_snapshot(
    *,
    total_physical: int,
    available_physical: int,
    commit_limit: int,
    available_commit: int,
    processes: Iterable[WindowsProcessReading],
) -> dict[str, int | None]:
    process_rows = list(processes)
    leaspac = [row for row in process_rows if row[0].lower() == "leaspac.exe"]
    return {
        "windows_total_physical_bytes": total_physical,
        "windows_available_physical_bytes": available_physical,
        "windows_commit_limit_bytes": commit_limit,
        "windows_committed_bytes": max(0, commit_limit - available_commit),
        "windows_available_commit_bytes": available_commit,
        "windows_leaspac_process_count": len(leaspac),
        "windows_leaspac_private_bytes": sum(row[2] for row in leaspac),
        "windows_largest_process_private_bytes": max((row[2] for row in process_rows), default=0),
    }


def read_training_memory_snapshot(
    *,
    platform_name: str | None = None,
    cgroup_root: str | Path = "/sys/fs/cgroup",
) -> dict[str, int | None]:
    platform_name = platform_name or os.name
    if platform_name != "nt":
        return read_cgroup_memory_snapshot(cgroup_root)
    try:
        total_physical, available_physical, commit_limit, available_commit = _read_windows_memory_status()
        return build_windows_memory_snapshot(
            total_physical=total_physical,
            available_physical=available_physical,
            commit_limit=commit_limit,
            available_commit=available_commit,
            processes=_read_windows_processes(),
        )
    except (AttributeError, OSError, ValueError):
        return {
            "windows_total_physical_bytes": None,
            "windows_available_physical_bytes": None,
            "windows_commit_limit_bytes": None,
            "windows_committed_bytes": None,
            "windows_available_commit_bytes": None,
            "windows_leaspac_process_count": None,
            "windows_leaspac_private_bytes": None,
            "windows_largest_process_private_bytes": None,
        }


def _read_windows_memory_status() -> tuple[int, int, int, int]:
    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError()
    return (
        int(status.ullTotalPhys),
        int(status.ullAvailPhys),
        int(status.ullTotalPageFile),
        int(status.ullAvailPageFile),
    )


def _read_windows_processes() -> list[WindowsProcessReading]:
    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("cntUsage", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", ctypes.c_ulong),
            ("cntThreads", ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", ctypes.c_ulong),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    class ProcessMemoryCountersEx(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid_handle = ctypes.c_void_p(-1).value
    if snapshot == invalid_handle:
        raise ctypes.WinError()
    rows: list[WindowsProcessReading] = []
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(entry)
        success = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while success:
            process = kernel32.OpenProcess(0x0400 | 0x0010, False, entry.th32ProcessID)
            if process:
                try:
                    counters = ProcessMemoryCountersEx()
                    counters.cb = ctypes.sizeof(counters)
                    if psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
                        rows.append((entry.szExeFile, int(entry.th32ProcessID), int(counters.PrivateUsage)))
                finally:
                    kernel32.CloseHandle(process)
            success = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return rows
