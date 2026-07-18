from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class TrainingRecoveryOptions:
    can_safe_retry: bool
    can_evaluate_best: bool
    best_weight_path: str | None
    preserved_artifact_count: int
    reason: str


@dataclass(frozen=True)
class TrainingFailureDiagnostic:
    schema_version: int
    code: str
    summary: str
    action: str
    technical_message: str
    exception_type: str | None
    traceback: str | None
    exit_code: int | None
    failure_phase: str
    failure_scope: str
    last_successful_epoch: int | None
    total_epochs: int | None
    occurred_at: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    resource_snapshot: dict[str, int | None] = field(default_factory=dict)
    recoverability: TrainingRecoveryOptions | None = None

    def model_dump(self) -> dict:
        return asdict(self)


_PRESENTATION = {
    "resource_limit": (
        "训练进程被外部强制终止，通常与内存或容器资源限制有关",
        "使用 CPU 安全配置重试，并降低图像尺寸或 Batch",
    ),
    "disk_full": ("训练存储空间不足", "清理磁盘或扩容后重试"),
    "device_unavailable": ("所选训练设备不可用", "改用可用设备，云端无 GPU 时请选择 CPU"),
    "base_model_unavailable": ("基础模型无法加载", "检查模型名称、权重文件和网络后重试"),
    "dataset_invalid": ("训练数据集无效或文件缺失", "检查数据集版本、图片和标注后重新发布"),
    "dependency_import": ("训练依赖未正确安装", "重新构建训练镜像并检查依赖版本"),
    "runner_failed": ("训练进程异常退出", "查看技术诊断和日志，修正原因后重试"),
}


def classify_training_failure(
    *,
    exit_code: int | None,
    message: str,
    log_tail: list[str],
    failure_phase: str,
    last_successful_epoch: int | None,
    total_epochs: int | None,
    best_weight_path: str | None,
    preserved_artifact_count: int,
    exception_type: str | None = None,
    traceback: str | None = None,
    occurred_at: str | None = None,
    resource_snapshot: dict[str, int | None] | None = None,
) -> TrainingFailureDiagnostic:
    combined = "\n".join([message, *log_tail]).lower()
    evidence: list[str] = []

    if exit_code in {-9, 137}:
        code = "resource_limit"
        evidence.append(f"process exit code {exit_code} indicates an external SIGKILL")
    else:
        signatures = (
            ("disk_full", ("no space left on device", "errno 28")),
            ("device_unavailable", ("invalid cuda device", "cuda is not available", "no cuda gpus are available")),
            ("dependency_import", ("modulenotfounderror", "no module named", "importerror")),
            ("dataset_invalid", ("dataset images not found", "dataset not found", "no images found", "labels not found")),
            ("base_model_unavailable", ("model not found", ".pt not found", "failed to download", "unable to load model")),
        )
        code = "runner_failed"
        for candidate, needles in signatures:
            match = next((needle for needle in needles if needle in combined), None)
            if match:
                code = candidate
                evidence.append(f"failure text contains: {match}")
                break

    scope = "post_training" if failure_phase in {"evaluation", "evaluating", "export", "exporting", "verification", "verifying"} else "training"
    can_evaluate = scope == "post_training" and bool(best_weight_path)
    recovery = TrainingRecoveryOptions(
        can_safe_retry=scope == "training",
        can_evaluate_best=can_evaluate,
        best_weight_path=best_weight_path,
        preserved_artifact_count=preserved_artifact_count,
        reason=("可使用已保存的最佳权重继续独立评估" if can_evaluate else "需要重新运行训练"),
    )
    summary, action = _PRESENTATION[code]
    return TrainingFailureDiagnostic(
        schema_version=1,
        code=code,
        summary=summary,
        action=action,
        technical_message=message or f"Runner exited with code {exit_code}",
        exception_type=exception_type,
        traceback=traceback,
        exit_code=exit_code,
        failure_phase=failure_phase,
        failure_scope=scope,
        last_successful_epoch=last_successful_epoch,
        total_epochs=total_epochs,
        occurred_at=occurred_at or datetime.now(timezone.utc).isoformat(),
        evidence=tuple(evidence),
        resource_snapshot=resource_snapshot or {},
        recoverability=recovery,
    )
