import pytest

from yolo_factory.training.presets import resolve_training_preset


def test_resolves_cpu_segmentation_balanced_preset() -> None:
    preset = resolve_training_preset("cpu-balanced", task_type="segment", device="cpu")

    assert preset.model_dump() == {
        "preset_id": "cpu-balanced",
        "epochs": 150,
        "batch": 1,
        "image_size": 640,
        "patience": 25,
        "optimizer": "auto",
        "close_mosaic": 10,
        "augment_profile": "conservative",
        "augmentation": {
            "mosaic": 0.5, "mixup": 0.0, "copy_paste": 0.0,
            "degrees": 5.0, "translate": 0.1, "scale": 0.3,
            "fliplr": 0.0, "hsv_h": 0.01, "hsv_s": 0.5, "hsv_v": 0.3,
        },
    }


def test_rejects_gpu_profile_on_cpu() -> None:
    with pytest.raises(ValueError, match="requires CUDA"):
        resolve_training_preset("gpu-quality", task_type="detect", device="cpu")


def test_smoke_is_bounded_on_every_device() -> None:
    assert resolve_training_preset("smoke", task_type="detect", device="cuda:0").batch == 1
    assert resolve_training_preset("smoke", task_type="segment", device="cpu").image_size == 320
