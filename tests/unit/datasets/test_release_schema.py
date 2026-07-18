import pytest
from pydantic import ValidationError

from yolo_factory.api.schemas import DatasetReleaseRequest


def test_dataset_release_request_requires_and_trims_display_name() -> None:
    request = DatasetReleaseRequest(
        task_id="inspection",
        annotation_import_id="annotation-1",
        display_name="  电梯标识数据集  ",
        version="0.1.0",
    )
    assert request.display_name == "电梯标识数据集"

    with pytest.raises(ValidationError):
        DatasetReleaseRequest(
            task_id="inspection",
            annotation_import_id="annotation-1",
            display_name="   ",
            version="0.1.0",
        )
