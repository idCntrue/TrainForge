from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

from yolo_factory.manifests.writer import write_manifest
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import FrameAsset

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class SelectionSummary:
    candidate: int
    selected: int
    rejected: int
    duplicate: int
    manifest_path: Path


def _selection_files(batch_dir: Path) -> list[tuple[Path, str, str | None]]:
    located: list[tuple[Path, str, str | None]] = []
    for directory_name, status in (
        ("candidates", "candidate"),
        ("selected", "selected"),
    ):
        directory = batch_dir / directory_name
        if directory.exists():
            located.extend(
                (path, status, None)
                for path in sorted(directory.iterdir())
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            )

    rejected_root = batch_dir / "rejected"
    if rejected_root.exists():
        for reason_dir in sorted(rejected_root.iterdir()):
            if not reason_dir.is_dir():
                continue
            located.extend(
                (path, "rejected", reason_dir.name)
                for path in sorted(reason_dir.iterdir())
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            )
    return located


def sync_selection(
    batch_id: str,
    batch_dir: Path,
    registry: Registry,
) -> SelectionSummary:
    manifest_path = batch_dir / "selection-manifest.yaml"
    located = _selection_files(batch_dir)

    with session_scope(registry) as session:
        registered_frames = list(
            session.scalars(
                select(FrameAsset)
                .where(FrameAsset.batch_id == batch_id)
                .order_by(FrameAsset.id)
            )
        )
        by_filename = {Path(frame.stored_path).name: frame for frame in registered_frames}
        unknown = [path.name for path, _, _ in located if path.name not in by_filename]
        if unknown:
            raise ValueError(
                "unregistered files in selection folders: "
                + ", ".join(sorted(unknown))
            )

        frames = [frame for frame in registered_frames if frame.lifecycle_status == "active"]
        active_ids = {frame.id for frame in frames}
        for path, status, reason in located:
            frame = by_filename[path.name]
            if frame.id not in active_ids:
                continue
            frame.stored_path = path.as_posix()
            frame.status = status
            frame.rejection_reason = reason

        manifest_frames = [
            {
                "id": frame.id,
                "path": frame.stored_path,
                "status": frame.status,
                "rejection_reason": frame.rejection_reason,
            }
            for frame in frames
        ]
        counts = {
            status: sum(frame.status == status for frame in frames)
            for status in ("candidate", "selected", "rejected", "duplicate")
        }

    write_manifest(
        manifest_path,
        {
            "batch_id": batch_id,
            "frames": manifest_frames,
            "summary": counts,
        },
    )
    return SelectionSummary(
        candidate=counts["candidate"],
        selected=counts["selected"],
        rejected=counts["rejected"],
        duplicate=counts["duplicate"],
        manifest_path=manifest_path,
    )
