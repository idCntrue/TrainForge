import json
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from yolo_factory.annotations.repository import AnnotationRepository
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
        (labels / f"{source.stem}.txt").write_text("\n".join(rows) + "\n", encoding="utf-8")
        with session_scope(registry) as session:
            frame = session.get(FrameAsset, item.frame_id)
            source_group = frame.video_id if frame is not None else item.frame_id
        source_index.append({"frame_id": item.frame_id, "image_name": source.name, "source_group": source_group})
    (extracted / "source-index.json").write_text(
        json.dumps(source_index, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    archive = root / "original.zip"
    with zipfile.ZipFile(archive, "w"):
        pass
    with session_scope(registry) as session:
        session.add(AnnotationExport(id=export_id, task_id=task_id, provider_project="native", provider_version=export_name, zip_path=archive.relative_to(storage_root).as_posix(), sha256="native"))
    return NativeAnnotationExport(export_id, extracted, len(reviewed))
