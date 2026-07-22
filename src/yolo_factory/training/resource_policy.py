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


class InsufficientTrainingMemory(RuntimeError):
    """Raised when Windows cannot safely commit memory for a training process."""

    def __init__(
        self,
        *,
        available_commit_gib: float | None,
        available_physical_gib: float | None,
        required_commit_gib: int,
        required_physical_gib: int,
        leaspac_process_count: int | None,
        leaspac_private_gib: float | None,
        failed_checks: tuple[str, ...],
    ) -> None:
        self.available_commit_gib = available_commit_gib
        self.available_physical_gib = available_physical_gib
        self.required_commit_gib = required_commit_gib
        self.required_physical_gib = required_physical_gib
        self.leaspac_process_count = leaspac_process_count
        self.leaspac_private_gib = leaspac_private_gib
        self.failed_checks = failed_checks
        commit = "unknown" if available_commit_gib is None else f"{available_commit_gib:.2f} GiB"
        physical = "unknown" if available_physical_gib is None else f"{available_physical_gib:.2f} GiB"
        process_evidence = ""
        if leaspac_process_count:
            private = "unknown" if leaspac_private_gib is None else f"{leaspac_private_gib:.2f} GiB"
            process_evidence = f"; LeASPac.exe {leaspac_process_count} processes use {private}"
        super().__init__(
            "Windows training requires at least "
            f"{required_commit_gib} GiB available commit and {required_physical_gib} GiB available physical memory; "
            f"currently {commit} commit and {physical} physical are available{process_evidence}"
        )

    def as_detail(self) -> dict[str, Any]:
        process_evidence = ""
        if self.leaspac_process_count:
            private = "未知" if self.leaspac_private_gib is None else f"{self.leaspac_private_gib:.2f} GiB"
            process_evidence = f"；检测到 LeASPac.exe {self.leaspac_process_count} 个，共占用 {private}"
        commit = "未知" if self.available_commit_gib is None else f"{self.available_commit_gib:.2f} GiB"
        physical = "未知" if self.available_physical_gib is None else f"{self.available_physical_gib:.2f} GiB"
        return {
            "code": "insufficient_training_memory",
            "message": (
                "Windows 可用内存不足，无法安全启动训练；"
                f"剩余提交内存 {commit}（至少 {self.required_commit_gib} GiB），"
                f"可用物理内存 {physical}（至少 {self.required_physical_gib} GiB）"
                f"{process_evidence}。请关闭占用内存的程序后重试"
            ),
            "available_commit_gib": self.available_commit_gib,
            "available_physical_gib": self.available_physical_gib,
            "required_commit_gib": self.required_commit_gib,
            "required_physical_gib": self.required_physical_gib,
            "leaspac_process_count": self.leaspac_process_count,
            "leaspac_private_gib": self.leaspac_private_gib,
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
    min_available_commit_gb: int = 8
    min_available_memory_gb: int = 4

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
            "min_available_commit_gb": cls._positive_integer(
                environment, "TRAINING_MIN_AVAILABLE_COMMIT_GB", 8
            ),
            "min_available_memory_gb": cls._positive_integer(
                environment, "TRAINING_MIN_AVAILABLE_MEMORY_GB", 4
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
        return TrainingExecutionPolicy(workers=0, cache=False, cpu_threads=None)

    def validate_memory_snapshot(self, snapshot: Mapping[str, int | None]) -> None:
        self._validate_memory_snapshot(snapshot, check_physical=True)

    def validate_runtime_memory_snapshot(self, snapshot: Mapping[str, int | None]) -> None:
        self._validate_memory_snapshot(snapshot, check_physical=False)

    def _validate_memory_snapshot(
        self,
        snapshot: Mapping[str, int | None],
        *,
        check_physical: bool,
    ) -> None:
        available_commit = snapshot.get("windows_available_commit_bytes")
        available_physical = snapshot.get("windows_available_physical_bytes")
        if available_commit is None and available_physical is None:
            return
        failed_checks = tuple(
            check
            for check, failed in (
                ("commit", available_commit is not None and available_commit < self.min_available_commit_gb * 1024**3),
                (
                    "physical",
                    check_physical
                    and available_physical is not None
                    and available_physical < self.min_available_memory_gb * 1024**3,
                ),
            )
            if failed
        )
        if not failed_checks:
            return
        leaspac_private = snapshot.get("windows_leaspac_private_bytes")
        raise InsufficientTrainingMemory(
            available_commit_gib=(available_commit / 1024**3 if available_commit is not None else None),
            available_physical_gib=(available_physical / 1024**3 if available_physical is not None else None),
            required_commit_gib=self.min_available_commit_gb,
            required_physical_gib=self.min_available_memory_gb,
            leaspac_process_count=snapshot.get("windows_leaspac_process_count"),
            leaspac_private_gib=(leaspac_private / 1024**3 if leaspac_private is not None else None),
            failed_checks=failed_checks,
        )

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
