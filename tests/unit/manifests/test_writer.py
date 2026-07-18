from pathlib import Path

import yaml

from yolo_factory.manifests.writer import write_manifest


def test_write_manifest_replaces_atomically(tmp_path: Path) -> None:
    path = tmp_path / "manifest.yaml"
    path.write_text("version: old\n", encoding="utf-8")

    write_manifest(path, {"version": "new", "items": [2, 1]})

    assert yaml.safe_load(path.read_text(encoding="utf-8")) == {
        "items": [2, 1],
        "version": "new",
    }
    assert not path.with_suffix(".yaml.tmp").exists()

