import json
import re
from datetime import datetime, timezone
from pathlib import Path


SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _validate_id(value: str, label: str) -> None:
    if not SAFE_ID.fullmatch(value) or value in {".", ".."}:
        raise ValueError(f"invalid {label}")


def gate_runs_root(storage_root: Path, model_id: str) -> Path:
    _validate_id(model_id, "model id")
    return (storage_root / "model-versions" / model_id / "gate-runs").resolve()


def gate_run_directory(storage_root: Path, model_id: str, run_id: str) -> Path:
    _validate_id(run_id, "gate run id")
    root = gate_runs_root(storage_root, model_id)
    directory = root / run_id
    if directory.parent != root:
        raise ValueError("invalid gate run id")
    return directory


def _read_json(path: Path) -> dict | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _directory_size(directory: Path) -> int:
    return sum(
        path.stat().st_size
        for path in directory.rglob("*")
        if path.is_file() and not path.is_symlink()
    )


def _onnx_metadata(directory: Path, result: dict | None) -> dict | None:
    configured = ((result or {}).get("artifacts") or {}).get("onnx") or {}
    candidates = [Path(configured["path"])] if configured.get("path") else []
    candidates.extend((directory / "exported").glob("*.onnx") if (directory / "exported").is_dir() else [])
    for candidate in candidates:
        try:
            if candidate.is_symlink():
                continue
            resolved = candidate.resolve()
            if not resolved.is_relative_to(directory.resolve()) or not resolved.is_file():
                continue
        except OSError:
            continue
        return {
            "path": str(resolved),
            "size_bytes": resolved.stat().st_size,
            "sha256": configured.get("sha256"),
            "exists": True,
        }
    return None


def _status(result: dict | None) -> str:
    if result is None:
        return "incomplete"
    if not result.get("passed", False):
        return "blocked"
    if not (result.get("gates") or {}).get("mask_consistency", True):
        return "completed_with_warnings"
    return "completed"


def list_gate_runs(storage_root: Path, model_id: str, active_report_path: Path | None) -> list[dict]:
    root = gate_runs_root(storage_root, model_id)
    if not root.is_dir():
        return []
    active = active_report_path.resolve() if active_report_path else None
    runs = []
    for directory in root.iterdir():
        if not directory.is_dir() or directory.is_symlink():
            continue
        result_path = directory / "result.json"
        result = None if result_path.is_symlink() else _read_json(result_path)
        modified = directory.stat().st_mtime
        runs.append({
            "id": directory.name,
            "created_at": datetime.fromtimestamp(modified, timezone.utc).isoformat(),
            "status": _status(result),
            "active": active == result_path.resolve(),
            "gates": dict((result or {}).get("gates") or {}),
            "onnx": _onnx_metadata(directory, result),
            "report_path": str(result_path.resolve()) if result_path.is_file() else None,
            "total_size_bytes": _directory_size(directory),
            "diagnostics_available": bool(result and isinstance(result.get("samples"), list)),
        })
    return sorted(runs, key=lambda run: run["created_at"], reverse=True)


def read_gate_run_result(storage_root: Path, model_id: str, run_id: str) -> dict | None:
    directory = gate_run_directory(storage_root, model_id, run_id)
    if directory.is_symlink() or not directory.is_dir():
        return None
    result_path = directory / "result.json"
    if result_path.is_symlink() or not result_path.resolve().is_relative_to(directory.resolve()):
        return None
    return _read_json(result_path)
