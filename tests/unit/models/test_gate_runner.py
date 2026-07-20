from pathlib import Path

import cv2
import numpy as np
import pytest
import yaml

from yolo_factory.models.gate_runner import _compare, _samples, _write_comparison_overlay


def _write_data_yaml(tmp_path: Path, payload: object) -> Path:
    path = tmp_path / "data.yaml"
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_samples_requires_mapping_payload(tmp_path: Path) -> None:
    data_yaml = _write_data_yaml(tmp_path, ["not", "a", "mapping"])

    with pytest.raises(ValueError, match="data.yaml must contain a mapping"):
        _samples(data_yaml)


def test_samples_requires_validation_or_test_split(tmp_path: Path) -> None:
    data_yaml = _write_data_yaml(tmp_path, {"path": ".", "train": "images/train"})

    with pytest.raises(ValueError, match="data.yaml must define a non-empty 'val' or 'test' split path"):
        _samples(data_yaml)


def test_samples_rejects_non_string_dataset_root(tmp_path: Path) -> None:
    data_yaml = _write_data_yaml(tmp_path, {"path": 42, "val": "images/val"})

    with pytest.raises(ValueError, match="data.yaml 'path' must be a string"):
        _samples(data_yaml)


@pytest.mark.parametrize("value", [123, [], {}])
def test_samples_rejects_non_string_split_path(tmp_path: Path, value: object) -> None:
    data_yaml = _write_data_yaml(tmp_path, {"path": ".", "val": value})

    with pytest.raises(ValueError, match="data.yaml 'val' or 'test' split path must be a string"):
        _samples(data_yaml)


def test_samples_requires_existing_split_directory(tmp_path: Path) -> None:
    data_yaml = _write_data_yaml(tmp_path, {"path": ".", "val": "images/val"})

    with pytest.raises(ValueError, match="dataset split directory does not exist"):
        _samples(data_yaml)


def test_samples_requires_images_and_ignores_non_image_files(tmp_path: Path) -> None:
    image_root = tmp_path / "images" / "val"
    image_root.mkdir(parents=True)
    (image_root / "notes.txt").write_text("not an image", encoding="utf-8")
    data_yaml = _write_data_yaml(tmp_path, {"path": ".", "val": "images/val"})

    with pytest.raises(ValueError, match="dataset split directory contains no supported images"):
        _samples(data_yaml)


def test_samples_returns_evenly_distributed_supported_images(tmp_path: Path) -> None:
    image_root = tmp_path / "images" / "val"
    image_root.mkdir(parents=True)
    for name in (*[f"{index:02d}.jpg" for index in range(10)], "ignored.txt"):
        (image_root / name).write_bytes(b"image")
    data_yaml = _write_data_yaml(tmp_path, {"path": ".", "val": "images/val"})

    assert _samples(data_yaml, limit=5) == [
        str(image_root / name) for name in ("00.jpg", "02.jpg", "04.jpg", "07.jpg", "09.jpg")
    ]


def _item(box: list[float], confidence: float, mask: np.ndarray) -> dict:
    return {"class_id": 0, "box": box, "confidence": confidence, "mask": mask}


def test_compare_consumes_each_onnx_instance_even_when_a_pair_fails() -> None:
    full = np.ones((8, 8), dtype=np.float32)
    empty = np.zeros((8, 8), dtype=np.float32)
    pt_items = [
        _item([0, 0, 10, 10], 0.95, full),
        _item([1, 0, 11, 10], 0.90, empty),
    ]
    onnx_items = [
        _item([0, 0, 10, 10], 0.10, full),
        _item([3, 0, 13, 10], 0.90, empty),
    ]

    report = _compare(pt_items, onnx_items, "segment")

    assert [pair["onnx_index"] for pair in report["pairs"]] == [0, 1]
    assert len({pair["onnx_index"] for pair in report["pairs"]}) == 2
    assert report["pairs"][0]["passed"] is False


def test_writes_failed_segmentation_overlay(tmp_path: Path) -> None:
    source = tmp_path / "source.jpg"
    cv2.imwrite(str(source), np.full((40, 60, 3), 180, dtype=np.uint8))
    pt_mask = np.zeros((10, 15), dtype=np.float32)
    onnx_mask = np.zeros((10, 15), dtype=np.float32)
    pt_mask[2:8, 2:7] = 1
    onnx_mask[2:8, 8:13] = 1
    output = tmp_path / "comparison.jpg"

    _write_comparison_overlay(
        source,
        [_item([8, 8, 28, 32], 0.9, pt_mask)],
        [_item([32, 8, 52, 32], 0.9, onnx_mask)],
        [{"pt_index": 0, "onnx_index": 0, "passed": False}],
        output,
    )

    rendered = cv2.imread(str(output))
    assert output.is_file()
    assert rendered is not None
    assert rendered.shape[:2] == (40, 60)
