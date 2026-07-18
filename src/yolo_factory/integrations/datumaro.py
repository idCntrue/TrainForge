from pathlib import Path

from datumaro.components.dataset import Dataset


def validate_roboflow_detection_dataset(dataset_root: Path) -> int:
    dataset = Dataset.import_from(
        str(dataset_root),
        format="roboflow_yolo",
    )
    sample_count = len(dataset)
    if sample_count == 0:
        raise ValueError("annotation export contains no samples")
    return sample_count
