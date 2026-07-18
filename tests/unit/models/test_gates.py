from pathlib import Path

from yolo_factory.models.gates import box_iou, compare_predictions, file_metadata


def test_file_metadata_contains_size_and_sha256(tmp_path: Path) -> None:
    artifact = tmp_path / "best.pt"
    artifact.write_bytes(b"model")

    metadata = file_metadata(artifact)

    assert metadata["size_bytes"] == 5
    assert metadata["sha256"] == "9372c470eeadd5ecd9c3c74c2b3cb633f8e2f2fad799250a0f70d652b6b825e4"


def test_box_iou_and_prediction_consistency() -> None:
    assert box_iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    report = compare_predictions(
        [{"class_id": 1, "confidence": 0.9, "box": [0, 0, 10, 10]}],
        [{"class_id": 1, "confidence": 0.88, "box": [0.2, 0.1, 10.1, 10.2]}],
        box_iou_threshold=0.9,
        confidence_delta=0.1,
    )

    assert report["passed"] is True
    assert report["matched"] == 1


def test_prediction_consistency_rejects_class_mismatch() -> None:
    report = compare_predictions(
        [{"class_id": 1, "confidence": 0.9, "box": [0, 0, 10, 10]}],
        [{"class_id": 2, "confidence": 0.9, "box": [0, 0, 10, 10]}],
    )

    assert report["passed"] is False
