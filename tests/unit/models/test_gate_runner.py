from pathlib import Path

import pytest
import yaml

from yolo_factory.models.gate_runner import _samples


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


def test_samples_returns_sorted_supported_images_up_to_limit(tmp_path: Path) -> None:
    image_root = tmp_path / "images" / "val"
    image_root.mkdir(parents=True)
    for name in ("c.jpeg", "a.jpg", "b.png", "ignored.txt"):
        (image_root / name).write_bytes(b"image")
    data_yaml = _write_data_yaml(tmp_path, {"path": ".", "val": "images/val"})

    assert _samples(data_yaml, limit=2) == [str(image_root / "a.jpg"), str(image_root / "b.png")]
