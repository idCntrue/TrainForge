import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from yolo_factory.models.domain import ModelVersion, ModelVersionSpec
from yolo_factory.models.release_bundle import build_release_bundle


def test_release_bundle_contains_weights_and_ordered_classes_without_absolute_paths(tmp_path: Path) -> None:
    pt = tmp_path / "training-runs" / "run" / "weights" / "best.pt"
    onnx = tmp_path / "model-versions" / "model-1" / "gate-runs" / "gate-1" / "exported" / "source.onnx"
    pt.parent.mkdir(parents=True)
    onnx.parent.mkdir(parents=True)
    pt.write_bytes(b"pt")
    onnx.write_bytes(b"onnx")
    model = ModelVersion(
        id="model-1", spec=ModelVersionSpec("demo", "1.0.0", "segment", "run", "release", ("raw-a", "raw-b"), {"raw-a": "A"}, str(pt), {"map50": .8}),
        status="published", gates={"training": True, "pt": True, "onnx": True, "consistency": True},
        artifacts={"onnx": {"path": str(onnx)}}, environment={"ultralytics": "test"}, gate_report_path=None,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc), published_at=None, archived_at=None,
    )
    payload, filename = build_release_bundle(tmp_path, model)
    assert filename == "demo-v1.0.0.zip"
    with zipfile.ZipFile(__import__('io').BytesIO(payload)) as archive:
        assert set(["model.pt", "model.onnx", "classes.txt", "classes-indexed.txt", "data.yaml", "manifest.json", "checksums.sha256", "gate-summary.json", "README.txt"]).issubset(archive.namelist())
        assert archive.read("classes.txt").decode() == "A\nraw-b\n"
        assert json.loads(archive.read("manifest.json"))["files"]["pt"] == "model.pt"
        assert str(tmp_path) not in archive.read("manifest.json").decode()
