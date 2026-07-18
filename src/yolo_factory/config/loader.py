from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

from yolo_factory.config.models import SystemConfig, TaskConfig

ConfigModel = TypeVar("ConfigModel", bound=BaseModel)


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"configuration must be a mapping: {path}")
    return data


def load_system_config(path: Path) -> SystemConfig:
    return SystemConfig.model_validate(_load_yaml(path))


def load_task_config(path: Path) -> TaskConfig:
    return TaskConfig.model_validate(_load_yaml(path))

