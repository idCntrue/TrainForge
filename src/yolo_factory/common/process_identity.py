from __future__ import annotations

import os
import subprocess
from pathlib import Path


class ProcessOwnershipError(RuntimeError):
    pass


def process_command_line(pid: int, *, platform_name: str | None = None) -> str | None:
    platform_name = platform_name or os.name
    try:
        if platform_name == "nt":
            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
            value = result.stdout.strip()
            return value or None
        proc_command = Path(f"/proc/{pid}/cmdline")
        if proc_command.is_file():
            return proc_command.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="replace").strip() or None
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        value = result.stdout.strip()
        return value or None
    except (OSError, subprocess.SubprocessError):
        return None


def verify_persisted_process(
    *,
    pid: int,
    command_line: str | None,
    token: str | None,
    manifest_path: Path,
    module_name: str,
) -> None:
    expected_manifest = str(manifest_path.resolve())
    token_matches = bool(token and command_line and token in command_line)
    legacy_matches = bool(
        not token
        and command_line
        and module_name in command_line
        and expected_manifest in command_line
    )
    if not token_matches and not legacy_matches:
        raise ProcessOwnershipError(
            f"Refusing to terminate PID {pid}: persisted runner identity does not match the live process"
        )
