import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import select

from yolo_factory.common.hashing import sha256_file
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import (
    FrameAsset,
    FrameBatch,
    VideoAsset,
    VideoCollection,
)

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class PackageResult:
    path: Path
    sha256: str
    image_count: int


def _write_entry(
    archive: zipfile.ZipFile,
    name: str,
    content: bytes,
) -> None:
    info = zipfile.ZipInfo(name, date_time=ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    archive.writestr(info, content)


def build_roboflow_package(
    task_id: str,
    frame_batch_id: str,
    output_zip: Path,
    registry: Registry,
) -> PackageResult:
    with session_scope(registry) as session:
        statement = (
            select(FrameAsset, VideoAsset)
            .join(VideoAsset, FrameAsset.video_id == VideoAsset.id)
            .join(FrameBatch, FrameAsset.batch_id == FrameBatch.id)
            .join(
                VideoCollection,
                FrameBatch.collection_id == VideoCollection.id,
            )
            .where(
                FrameAsset.batch_id == frame_batch_id,
                FrameAsset.status == "selected",
                FrameAsset.lifecycle_status == "active",
                VideoCollection.task_id == task_id,
            )
            .order_by(FrameAsset.id)
        )
        selected = list(session.execute(statement).all())

    if not selected:
        raise ValueError(
            f"no selected frames for batch: {frame_batch_id}"
        )

    source_map = io.StringIO(newline="")
    writer = csv.DictWriter(
        source_map,
        fieldnames=[
            "image",
            "frame_id",
            "source_video",
            "source_video_id",
            "timestamp_ms",
            "frame_index",
        ],
        lineterminator="\n",
    )
    writer.writeheader()

    image_entries: list[tuple[str, bytes]] = []
    for frame, video in selected:
        image_path = Path(frame.stored_path)
        image_entries.append(
            (f"images/{image_path.name}", image_path.read_bytes())
        )
        writer.writerow(
            {
                "image": image_path.name,
                "frame_id": frame.id,
                "source_video": video.original_name,
                "source_video_id": video.id,
                "timestamp_ms": frame.timestamp_ms,
                "frame_index": frame.frame_index,
            }
        )

    manifest_bytes = yaml.safe_dump(
        {
            "frame_batch_id": frame_batch_id,
            "image_count": len(image_entries),
            "task_id": task_id,
        },
        allow_unicode=True,
        sort_keys=True,
    ).encode("utf-8")
    source_map_bytes = source_map.getvalue().encode("utf-8")

    output_zip.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_zip.with_suffix(output_zip.suffix + ".tmp")
    with zipfile.ZipFile(temporary, mode="w") as archive:
        for name, content in sorted(image_entries):
            _write_entry(archive, name, content)
        _write_entry(archive, "package-manifest.yaml", manifest_bytes)
        _write_entry(archive, "source-map.csv", source_map_bytes)
    temporary.replace(output_zip)

    return PackageResult(
        path=output_zip,
        sha256=sha256_file(output_zip),
        image_count=len(image_entries),
    )
