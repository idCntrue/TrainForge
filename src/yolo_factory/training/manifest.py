import json
import sys
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Mapping

from yolo_factory.common.hashing import sha256_file
from yolo_factory.training.models import TrainingRunSpec
from yolo_factory.training.resource_policy import TrainingExecutionPolicy


def write_manifest(
    path: Path,
    run_id: str,
    spec: TrainingRunSpec,
    *,
    engine: str,
    dataset_release_path: Path | None = None,
    data_yaml_path: Path | None = None,
    simulation_step_seconds: float | None = None,
    execution: TrainingExecutionPolicy | None = None,
    environment: Mapping[str, str] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "engine": engine,
        "spec": asdict(spec),
        "environment": dict(environment or _runtime_environment()),
        "inputs": {
            "dataset_release_id": spec.dataset_release_id,
            "base_model": _model_identity(spec.base_model),
        },
    }
    if dataset_release_path is not None or data_yaml_path is not None:
        if dataset_release_path is None or data_yaml_path is None:
            raise ValueError("dataset release path and data YAML path must be provided together")
        payload["dataset"] = {
            "release_path": str(dataset_release_path.resolve()),
            "data_yaml_path": str(data_yaml_path.resolve()),
        }
    if engine == "simulation":
        payload["simulation_step_seconds"] = simulation_step_seconds
    if execution is not None:
        payload["execution"] = execution.model_dump()
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
    return path


def _runtime_environment() -> dict[str, str]:
    packages = {}
    for name in ("torch", "ultralytics"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "not-installed"
    return {"python": sys.version.split()[0], **packages}


def _model_identity(base_model: str) -> dict[str, str | None]:
    path = Path(base_model).expanduser()
    return {
        "path": base_model,
        "sha256": sha256_file(path) if path.is_file() else None,
    }
