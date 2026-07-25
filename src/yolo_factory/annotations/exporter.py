import json
import shutil
import zipfile
import yaml
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from yolo_factory.annotations.repository import AnnotationRepository
from yolo_factory.common.hashing import sha256_file
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import AnnotationExport, FrameAsset, Task


@dataclass(frozen=True)
class NativeAnnotationExport:
    export_id: str
    extracted_root: Path
    sample_count: int


def export_reviewed_annotations(task_id: str, export_name: str, storage_root: Path, registry: Registry) -> NativeAnnotationExport:
    export_id = f"annotation-{task_id}-native-{export_name}"
    root = storage_root / "annotation-exports" / task_id / "native" / export_name
    extracted = root / "extracted"
    with session_scope(registry) as session:
        task = session.get(Task, task_id)
        if task is None:
            raise KeyError(task_id)
        existing = session.get(AnnotationExport, export_id)
        if existing is not None:
            raise ValueError(f"native annotation export already exists: {export_id}; use a new export name")
        classes = json.loads(task.classes_json)
    reviewed = AnnotationRepository(registry).list(task_id=task_id, status="reviewed")
    if not reviewed:
        raise ValueError("no reviewed annotations to export")
    shutil.rmtree(extracted, ignore_errors=True)
    images = extracted / "train" / "images"
    labels = extracted / "train" / "labels"
    images.mkdir(parents=True)
    labels.mkdir(parents=True)
    source_index = []
    for item in reviewed:
        source = Path(item.image_path)
        shutil.copy2(source, images / source.name)
        rows = []
        for shape in item.shapes:
            expected = "box" if item.task_type == "detect" else "polygon"
            if shape.shape_type != expected:
                raise ValueError(f"shape type mismatch for {item.frame_id}")
            rows.append(f"{shape.class_id} " + " ".join(f"{value:.6f}" for value in shape.coordinates))
        label_content = "\n".join(rows) + ("\n" if rows else "")
        (labels / f"{source.stem}.txt").write_text(label_content, encoding="utf-8")
        with session_scope(registry) as session:
            frame = session.get(FrameAsset, item.frame_id)
            source_group = frame.video_id if frame is not None else item.frame_id
        source_index.append({"frame_id": item.frame_id, "image_name": source.name, "source_group": source_group})
    (extracted / "source-index.json").write_text(
        json.dumps(source_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (extracted / "classes.txt").write_text("\n".join(classes) + "\n", encoding="utf-8")
    (extracted / "data.yaml").write_text(
        yaml.safe_dump({
            "path": ".",
            "train": "train/images",
            "val": "train/images",
            "nc": len(classes),
            "names": classes,
        }, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    archive = root / "original.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(item for item in extracted.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(extracted).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    digest = sha256_file(archive)
    with session_scope(registry) as session:
        session.add(AnnotationExport(id=export_id, task_id=task_id, provider_project="native", provider_version=export_name, zip_path=archive.relative_to(storage_root).as_posix(), sha256=digest))
    return NativeAnnotationExport(export_id, extracted, len(reviewed))
