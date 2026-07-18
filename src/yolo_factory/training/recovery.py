from dataclasses import dataclass


@dataclass(frozen=True)
class SafeRetryPlan:
    allowed: bool
    batch: int
    image_size: int
    preset_id: str
    reason: str


@dataclass(frozen=True)
class EvaluationRecoveryPlan:
    allowed: bool
    best_weight_path: str | None
    reason: str


_PREREQUISITES = {
    "disk_full": "磁盘空间不足，请先清理或扩容",
    "dataset_invalid": "数据集无效，请修复并重新发布数据集",
    "base_model_unavailable": "基础模型不可用，请检查或重新上传权重",
    "device_unavailable": "训练设备不可用，请选择可用设备",
    "dependency_import": "训练依赖缺失，请重新构建训练镜像",
}
_IMAGE_STEPS = (640, 512, 416, 320)


def plan_safe_retry(
    *, task_type: str, device: str, batch: int, image_size: int, failure_code: str,
) -> SafeRetryPlan:
    del task_type
    if failure_code in _PREREQUISITES:
        return SafeRetryPlan(False, batch, image_size, "", _PREREQUISITES[failure_code])
    if failure_code not in {"resource_limit", "runner_failed"}:
        return SafeRetryPlan(False, batch, image_size, "", "该故障不支持自动安全重试")

    next_batch = max(1, batch // 2) if batch > 1 else batch
    next_image_size = image_size
    if batch <= 1:
        supported = [size for size in _IMAGE_STEPS if size < image_size]
        if not supported:
            return SafeRetryPlan(False, batch, image_size, "", "已达到最低安全参数，请先排查技术诊断")
        next_image_size = supported[0]
    preset_id = "cpu-balanced" if device.lower().startswith("cpu") else "gpu-quality"
    return SafeRetryPlan(True, next_batch, next_image_size, preset_id, "已降低单次训练资源占用")
