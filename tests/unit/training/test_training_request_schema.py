from yolo_factory.api.schemas import TrainingRunCreateRequest
from pydantic import ValidationError
import pytest


def test_server_preset_request_uses_safe_defaults_for_overridden_parameters() -> None:
    request = TrainingRunCreateRequest.model_validate(
        {
            "name": "test",
            "task_type": "segment",
            "dataset_release_id": "dataset-1",
            "base_model": "yolo26s-seg.pt",
            "selected_classes": ["sign"],
            "preset_id": "cpu-balanced",
        }
    )

    assert request.device == "cpu"
    assert request.epochs == 100
    assert request.batch == 1
    assert request.image_size == 320


def test_training_request_rejects_image_size_that_is_not_stride_aligned() -> None:
    with pytest.raises(ValidationError, match="multiple of 32"):
        TrainingRunCreateRequest.model_validate(
            {
                "name": "invalid-size",
                "task_type": "detect",
                "dataset_release_id": "dataset-1",
                "base_model": "yolo11n.pt",
                "selected_classes": ["sign"],
                "image_size": 650,
            }
        )
