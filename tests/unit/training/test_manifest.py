import json
from pathlib import Path

from yolo_factory.training.manifest import write_manifest
from yolo_factory.training.models import TrainingRunSpec


def test_manifest_records_reproducible_environment_and_weight_hash(tmp_path: Path) -> None:
    weight = tmp_path / "base.pt"
    weight.write_bytes(b"base-weight")
    path = write_manifest(
        tmp_path / "manifest.json",
        "run-1",
        TrainingRunSpec("run", "detect", "release-1", str(weight), 10, 1, 320, "cpu"),
        engine="ultralytics",
        environment={"python": "3.10.0", "torch": "2.8.0", "ultralytics": "8.4.95"},
    )

    manifest = json.loads(path.read_text(encoding="utf-8"))

    assert manifest["environment"] == {"python": "3.10.0", "torch": "2.8.0", "ultralytics": "8.4.95"}
    assert manifest["inputs"]["dataset_release_id"] == "release-1"
    assert manifest["inputs"]["base_model"]["path"] == str(weight)
    assert len(manifest["inputs"]["base_model"]["sha256"]) == 64
