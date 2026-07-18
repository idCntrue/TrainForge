from __future__ import annotations

import shutil
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


class UnsafeTrainingConfiguration(ValueError):
    """Raised when a CPU training request exceeds the configured safety limits."""


class InsufficientTrainingStorage(RuntimeError):
    """Raised when the training volume does not have enough free space."""

    def __init__(
        self,
        *,
        free_gib: float,
        free_percent: float,
        required_gib: int,
        required_percent: int,
        failed_checks: tuple[str, ...],
    ) -> None:
        self.free_gib = free_gib
        self.free_percent = free_percent
        self.required_gib = required_gib
        self.required_percent = required_percent
        self.failed_checks = failed_checks
        super().__init__(
            "Training requires at least "
            f"{required_gib} GiB and {required_percent}% free disk; "
            f"currently {free_gib:.2f} GiB ({free_percent:.2f}%) is free"
        )

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": "insufficient_training_storage",
            "message": (
                f"训练至少需要 {self.required_gib} GiB 可用空间且保持 "
                f"{self.required_percent}% 空闲；当前为 {self.free_gib:.2f} GiB"
                f"（{self.free_percent:.2f}%）"
            ),
            "free_gib": round(self.free_gib, 2),
            "free_percent": round(self.free_percent, 2),
            "required_gib": self.required_gib,
            "required_percent": self.required_percent,
            "failed_checks": list(self.failed_checks),
        }


@dataclass(frozen=True)
class TrainingExecutionPolicy:
    workers: int
    cache: bool
    cpu_threads: int | None

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrainingResourcePolicy:
    cpu_threads: int = 4
    detect_max_batch: int = 4
    segment_max_batch: int = 1
    max_image_size: int = 640
    gpu_detect_max_batch: int = 8
    gpu_segment_max_batch: int = 2
    gpu_max_image_size: int = 1280
    gpu_allowed_devices: tuple[str, ...] = ()
    min_free_disk_gb: int = 8
    min_free_disk_percent: int = 10

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "TrainingResourcePolicy":
        values = {
            "cpu_threads": cls._positive_integer(environment, "CPU_TRAINING_THREADS", 4),
            "detect_max_batch": cls._positive_integer(environment, "CPU_DETECT_MAX_BATCH", 4),
            "segment_max_batch": cls._positive_integer(environment, "CPU_SEGMENT_MAX_BATCH", 1),
            "max_image_size": cls._positive_integer(environment, "CPU_TRAINING_MAX_IMAGE_SIZE", 640),
            "gpu_detect_max_batch": cls._positive_integer(environment, "GPU_DETECT_MAX_BATCH", 8),
            "gpu_segment_max_batch": cls._positive_integer(environment, "GPU_SEGMENT_MAX_BATCH", 2),
            "gpu_max_image_size": cls._positive_integer(environment, "GPU_TRAINING_MAX_IMAGE_SIZE", 1280),
            "gpu_allowed_devices": tuple(
                device.strip().lower()
                for device in environment.get("GPU_ALLOWED_DEVICES", "").split(",")
                if device.strip()
            ),
            "min_free_disk_gb": cls._positive_integer(environment, "TRAINING_MIN_FREE_DISK_GB", 8),
            "min_free_disk_percent": cls._positive_integer(
                environment, "TRAINING_MIN_FREE_DISK_PERCENT", 10
            ),
        }
        if values["min_free_disk_percent"] > 100:
            raise ValueError("TRAINING_MIN_FREE_DISK_PERCENT must be at most 100")
        return cls(**values)

    @staticmethod
    def _positive_integer(environment: Mapping[str, str], name: str, default: int) -> int:
        raw = environment.get(name, str(default))
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be a positive integer") from exc
        if value <= 0:
            raise ValueError(f"{name} must be a positive integer")
        return value

    def validate_request(self, task_type: str, device: str, *, batch: int, image_size: int) -> None:
        normalized_device = device.lower()
        if not normalized_device.startswith("cpu"):
            if self.gpu_allowed_devices and normalized_device not in self.gpu_allowed_devices:
                raise UnsafeTrainingConfiguration(
                    f"GPU device {device} is not permitted by GPU_ALLOWED_DEVICES"
                )
            max_batch = self.gpu_segment_max_batch if task_type == "segment" else self.gpu_detect_max_batch
            task_name = "segmentation" if task_type == "segment" else "detection"
            if batch > max_batch:
                raise UnsafeTrainingConfiguration(
                    f"GPU {task_name} training batch must be at most {max_batch}"
                )
            if image_size > self.gpu_max_image_size:
                raise UnsafeTrainingConfiguration(
                    f"GPU training image size must be at most {self.gpu_max_image_size}"
                )
            return

        max_batch = self.segment_max_batch if task_type == "segment" else self.detect_max_batch
        task_name = "segmentation" if task_type == "segment" else "detection"
        if batch > max_batch:
            raise UnsafeTrainingConfiguration(
                f"CPU {task_name} training batch must be at most {max_batch}"
            )
        if image_size > self.max_image_size:
            raise UnsafeTrainingConfiguration(
                f"CPU training image size must be at most {self.max_image_size}"
            )

    def execution_policy(self, device: str) -> TrainingExecutionPolicy:
        if device.lower().startswith("cpu"):
            return TrainingExecutionPolicy(workers=0, cache=False, cpu_threads=self.cpu_threads)
        return TrainingExecutionPolicy(workers=2, cache=False, cpu_threads=None)

    def validate_free_disk(
        self,
        path: str | Path,
        *,
        usage: Callable[[str | Path], Any] = shutil.disk_usage,
    ) -> None:
        disk = usage(path)
        free_gib = disk.free / (1024**3)
        free_percent = (disk.free / disk.total * 100) if disk.total else 0
        if free_gib < self.min_free_disk_gb or free_percent < self.min_free_disk_percent:
            failed_checks = tuple(
                check
                for check, failed in (
                    ("absolute", free_gib < self.min_free_disk_gb),
                    ("percentage", free_percent < self.min_free_disk_percent),
                )
                if failed
            )
            raise InsufficientTrainingStorage(
                free_gib=free_gib,
                free_percent=free_percent,
                required_gib=self.min_free_disk_gb,
                required_percent=self.min_free_disk_percent,
                failed_checks=failed_checks,
            )
