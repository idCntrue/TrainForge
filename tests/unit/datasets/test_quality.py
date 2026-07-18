from pathlib import Path

import yaml

from yolo_factory.datasets.quality import analyze_dataset_quality


def _release(tmp_path: Path, counts: dict[str, dict[int, int]]) -> Path:
    release = tmp_path / "release"
    for split, class_counts in counts.items():
        images = release / "images" / split
        labels = release / "labels" / split
        images.mkdir(parents=True)
        labels.mkdir(parents=True)
        index = 0
        for class_id, count in class_counts.items():
            for _ in range(count):
                (images / f"image-{index}.jpg").write_bytes(b"jpg")
                (labels / f"image-{index}.txt").write_text(
                    f"{class_id} 0.5 0.5 0.2 0.2\n", encoding="utf-8",
                )
                index += 1
    (release / "data.yaml").write_text(yaml.safe_dump({
        "path": ".", "train": "images/train", "val": "images/val", "test": "images/test",
        "names": ["sign", "light"],
    }), encoding="utf-8")
    return release


def test_reports_split_and_per_class_evidence(tmp_path: Path) -> None:
    release = _release(tmp_path, {
        "train": {0: 60, 1: 10}, "val": {0: 15, 1: 5}, "test": {0: 8, 1: 2},
    })

    report = analyze_dataset_quality(release, class_names=["sign", "light"])

    assert report.split_images == {"train": 70, "val": 20, "test": 10}
    assert report.class_instances["sign"]["test"] == 8
    assert "test_class_evidence_low:sign" in report.warnings
    assert report.blockers == []


def test_blocks_empty_validation_split(tmp_path: Path) -> None:
    release = _release(tmp_path, {"train": {0: 1}, "val": {}, "test": {0: 1}})

    report = analyze_dataset_quality(release, class_names=["sign", "light"])

    assert "empty_val_split" in report.blockers


def test_blocks_missing_and_malformed_labels(tmp_path: Path) -> None:
    release = _release(tmp_path, {"train": {0: 1}, "val": {0: 1}, "test": {0: 1}})
    (release / "labels" / "train" / "image-0.txt").unlink()
    (release / "labels" / "val" / "image-0.txt").write_text("9 broken\n", encoding="utf-8")

    report = analyze_dataset_quality(release, class_names=["sign", "light"])

    assert report.missing_label_files
    assert "missing_label_files" in report.blockers
    assert "malformed_or_out_of_range_labels" in report.blockers
