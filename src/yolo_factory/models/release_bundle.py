import hashlib
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from yolo_factory.models.domain import ModelVersion


class ReleaseBundleError(ValueError):
    pass


def _inside(root: Path, value: str, label: str) -> Path:
    candidate = Path(value).expanduser().resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ReleaseBundleError(f"{label} is outside storage root") from exc
    if not candidate.is_file():
        raise ReleaseBundleError(f"{label} is missing")
    return candidate


def _safe_stem(value: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return stem or "model"


def _classes(model: ModelVersion) -> list[str]:
    return [model.spec.class_aliases.get(name, name) for name in model.spec.selected_classes]


def build_release_bundle(storage_root: Path, model: ModelVersion) -> tuple[bytes, str]:
    if model.status not in {"published", "archived"}:
        raise ReleaseBundleError("only published or archived models can be exported")
    root = storage_root.resolve()
    pt = _inside(root, model.spec.pt_path, "model PT artifact")
    onnx_info = model.artifacts.get("onnx")
    if not onnx_info or not onnx_info.get("path"):
        raise ReleaseBundleError("published model ONNX artifact is missing")
    onnx = _inside(root, str(onnx_info["path"]), "model ONNX artifact")
    names = _classes(model)
    if not names:
        raise ReleaseBundleError("model class metadata is missing")

    manifest = {
        "schema_version": 1,
        "name": model.spec.name,
        "version": model.spec.version,
        "model_id": model.id,
        "task_type": model.spec.task_type,
        "dataset_release_id": model.spec.dataset_release_id,
        "training_run_id": model.spec.training_run_id,
        "classes": names,
        "metrics": model.spec.metrics,
        "status": model.status,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "files": {"pt": "model.pt", "onnx": "model.onnx", "classes": "classes.txt", "data": "data.yaml"},
    }
    gate_summary = {"gates": model.gates, "environment": model.environment}
    data_yaml = yaml.safe_dump({"nc": len(names), "names": names}, allow_unicode=True, sort_keys=False)
    files = {
        "model.pt": pt.read_bytes(),
        "model.onnx": onnx.read_bytes(),
        "classes.txt": ("\n".join(names) + "\n").encode("utf-8"),
        "classes-indexed.txt": ("\n".join(f"{index}\t{name}" for index, name in enumerate(names)) + "\n").encode("utf-8"),
        "data.yaml": data_yaml.encode("utf-8"),
        "manifest.json": (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        "gate-summary.json": (json.dumps(gate_summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        "README.txt": ("TrainForge model release\n\nmodel.pt and model.onnx use the class order in classes.txt.\n" "Verify checksums.sha256 before deployment.\n").encode("utf-8"),
    }
    hashes = "".join(f"{hashlib.sha256(payload).hexdigest()}  {name}\n" for name, payload in files.items())
    files["checksums.sha256"] = hashes.encode("ascii")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(files):
            archive.writestr(name, files[name])
    filename = f"{_safe_stem(model.spec.name)}-v{_safe_stem(model.spec.version)}.zip"
    return buffer.getvalue(), filename
