from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ResolvedTrainingPreset:
    preset_id: str
    epochs: int
    batch: int
    image_size: int
    patience: int
    optimizer: str
    close_mosaic: int
    augment_profile: str
    augmentation: dict[str, float]

    def model_dump(self) -> dict:
        return asdict(self)


_CONSERVATIVE_AUGMENTATION = dict(mosaic=0.5, mixup=0.0, copy_paste=0.0, degrees=5.0, translate=0.1, scale=0.3, fliplr=0.0, hsv_h=0.01, hsv_s=0.5, hsv_v=0.3)
_STANDARD_AUGMENTATION = dict(mosaic=1.0, mixup=0.0, copy_paste=0.0, degrees=0.0, translate=0.1, scale=0.5, fliplr=0.5, hsv_h=0.015, hsv_s=0.7, hsv_v=0.4)


_PRESETS = {
    "smoke": dict(epochs=10, image_size=320, patience=5, optimizer="auto", close_mosaic=2, augment_profile="conservative", augmentation=_CONSERVATIVE_AUGMENTATION),
    "cpu-balanced": dict(epochs=150, image_size=640, patience=25, optimizer="auto", close_mosaic=10, augment_profile="conservative", augmentation=_CONSERVATIVE_AUGMENTATION),
    "gpu-quality": dict(epochs=200, image_size=640, patience=30, optimizer="auto", close_mosaic=10, augment_profile="standard", augmentation=_STANDARD_AUGMENTATION),
}


def resolve_training_preset(preset_id: str, *, task_type: str, device: str) -> ResolvedTrainingPreset:
    if preset_id not in _PRESETS:
        raise ValueError(f"unknown training preset: {preset_id}")
    is_cpu = device.lower().startswith("cpu")
    if preset_id == "gpu-quality" and is_cpu:
        raise ValueError("gpu-quality requires CUDA")
    if preset_id == "smoke":
        batch = 1
    elif is_cpu:
        batch = 1 if task_type == "segment" else 2
    else:
        batch = 8
    return ResolvedTrainingPreset(preset_id=preset_id, batch=batch, **_PRESETS[preset_id])
