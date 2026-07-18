from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SystemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_root: Path

    @model_validator(mode="after")
    def validate_storage_root(self) -> "SystemConfig":
        if not self.storage_root.is_absolute():
            raise ValueError("storage_root must be absolute")
        return self


class TaskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    task_type: Literal["detect", "segment"]
    classes: list[str] = Field(min_length=1)
    class_display_names: dict[str, str] = Field(default_factory=dict)
    annotation_format: Literal["yolo-detect", "yolo-seg"]

    @model_validator(mode="after")
    def validate_task(self) -> "TaskConfig":
        expected_format = (
            "yolo-detect" if self.task_type == "detect" else "yolo-seg"
        )
        if self.annotation_format != expected_format:
            raise ValueError(
                f"{self.task_type} tasks require {expected_format}"
            )
        if len(set(self.classes)) != len(self.classes):
            raise ValueError("class names must be unique")
        if any(not class_name.strip() for class_name in self.classes):
            raise ValueError("class names must not be blank")
        if set(self.class_display_names) - set(self.classes):
            raise ValueError("class display names must target declared classes")
        return self
