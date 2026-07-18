import json
from pathlib import Path

import typer

from yolo_factory.annotations.import_service import import_roboflow_export
from yolo_factory.annotations.package_service import build_roboflow_package
from yolo_factory.config.loader import load_system_config, load_task_config
from yolo_factory.datasets.release import release_dataset
from yolo_factory.datasets.validation import validate_dataset
from yolo_factory.frames.deduplication import find_duplicate_groups
from yolo_factory.frames.extractor import extract_interval_frames
from yolo_factory.frames.selection import sync_selection
from yolo_factory.integrations.dvc import DvcAdapter
from yolo_factory.migrations.storage_paths import migrate_storage_paths
from yolo_factory.registry.database import Registry, create_registry, session_scope
from yolo_factory.registry.models import Task
from yolo_factory.video.import_service import import_video_collection
from yolo_factory.video.inspection import inspect_video

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
STORAGE_DIRECTORIES = (
    "raw-videos",
    "frame-batches",
    "annotation-packages",
    "annotation-exports",
    "dataset-releases",
    "dvc-cache",
    "registry",
    "staging",
    "quarantine",
    "logs",
)


def _context(system_path: Path) -> tuple[Path, Registry]:
    storage_root = load_system_config(system_path).storage_root
    return storage_root, create_registry(storage_root / "registry" / "factory.db")


def _register_task(task_path: Path, registry: Registry):
    task = load_task_config(task_path)
    with session_scope(registry) as session:
        existing = session.get(Task, task.task_id)
        classes_json = json.dumps(task.classes, ensure_ascii=False)
        if existing is None:
            session.add(
                Task(
                    id=task.task_id,
                    task_type=task.task_type,
                    annotation_format=task.annotation_format,
                    classes_json=classes_json,
                )
            )
        elif (
            existing.task_type != task.task_type
            or existing.annotation_format != task.annotation_format
            or existing.classes_json != classes_json
        ):
            raise ValueError(f"registered task contract differs: {task.task_id}")
    return task


@app.command("init-storage")
def init_storage(
    system: Path = typer.Option(..., exists=True, dir_okay=False),
) -> None:
    storage_root = load_system_config(system).storage_root
    for directory in STORAGE_DIRECTORIES:
        (storage_root / directory).mkdir(parents=True, exist_ok=True)
    create_registry(storage_root / "registry" / "factory.db")
    DvcAdapter(storage_root).initialize()
    typer.echo(storage_root)


@app.command("migrate-storage-paths")
def migrate_storage_paths_command(
    database: Path = typer.Option(..., exists=True, dir_okay=False),
    old_root: str = typer.Option(..., "--old-root"),
    new_root: Path = typer.Option(..., "--new-root"),
    apply: bool = typer.Option(False, "--apply", help="Apply changes after creating a SQLite backup."),
) -> None:
    report = migrate_storage_paths(database, old_root, new_root, apply=apply)
    typer.echo(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))


@app.command("video-import")
def video_import(
    task: Path = typer.Option(..., exists=True, dir_okay=False),
    source: Path = typer.Option(..., exists=True, file_okay=False),
    collection: str = typer.Option(...),
    system: Path = typer.Option(..., exists=True, dir_okay=False),
) -> None:
    storage_root, registry = _context(system)
    task_config = _register_task(task, registry)
    result = import_video_collection(
        task_config.task_id, collection, source, storage_root, registry
    )
    typer.echo(f"{result.collection_id} {result.manifest_path}")


@app.command("video-inspect")
def video_inspect(video: Path = typer.Option(..., exists=True, dir_okay=False)) -> None:
    typer.echo(json.dumps(inspect_video(video).__dict__, sort_keys=True))


@app.command("frame-extract")
def frame_extract(
    video: Path = typer.Option(..., exists=True, dir_okay=False),
    output: Path = typer.Option(...),
    collection: str = typer.Option(...),
    video_id: str = typer.Option(...),
    interval: float = typer.Option(1.0, min=0.001),
    quality: int = typer.Option(95, min=1, max=100),
) -> None:
    frames = extract_interval_frames(
        video, output, collection, video_id, interval, quality
    )
    typer.echo(f"frames={len(frames)} output={output}")


@app.command("frame-deduplicate")
def frame_deduplicate(
    images: Path = typer.Option(..., exists=True, file_okay=False),
    distance: int = typer.Option(6, min=0),
) -> None:
    paths = [
        path
        for path in images.rglob("*")
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    ]
    groups = find_duplicate_groups(paths, distance)
    typer.echo(
        json.dumps(
            [
                {
                    "canonical": str(group.canonical),
                    "duplicates": [str(path) for path in group.duplicates],
                }
                for group in groups
            ],
            sort_keys=True,
        )
    )


@app.command("selection-sync")
def selection_sync(
    batch: str = typer.Option(...),
    batch_dir: Path = typer.Option(..., exists=True, file_okay=False),
    system: Path = typer.Option(..., exists=True, dir_okay=False),
) -> None:
    _, registry = _context(system)
    result = sync_selection(batch, batch_dir, registry)
    typer.echo(result.manifest_path)


@app.command("annotation-package")
def annotation_package(
    task_id: str = typer.Option(..., "--task-id"),
    batch: str = typer.Option(...),
    output: Path = typer.Option(...),
    system: Path = typer.Option(..., exists=True, dir_okay=False),
) -> None:
    _, registry = _context(system)
    result = build_roboflow_package(task_id, batch, output, registry)
    typer.echo(f"{result.sha256} {result.path}")


@app.command("annotation-import")
def annotation_import(
    archive: Path = typer.Option(..., exists=True, dir_okay=False),
    task: Path = typer.Option(..., exists=True, dir_okay=False),
    project: str = typer.Option(...),
    provider_version: str = typer.Option(..., "--provider-version"),
    system: Path = typer.Option(..., exists=True, dir_okay=False),
) -> None:
    storage_root, registry = _context(system)
    task_config = _register_task(task, registry)
    result = import_roboflow_export(
        archive,
        task_config,
        project,
        provider_version,
        storage_root,
        registry,
    )
    typer.echo(f"{result.import_id} {result.extracted_root}")


@app.command("dataset-check")
def dataset_check(
    root: Path = typer.Option(..., exists=True, file_okay=False),
    task: Path = typer.Option(..., exists=True, dir_okay=False),
) -> None:
    result = validate_dataset(root, load_task_config(task))
    typer.echo(f"samples={result.sample_count} report={result.report_path}")
    if result.has_errors:
        raise typer.Exit(code=2)


@app.command("dataset-release")
def dataset_release(
    annotation_import_id: str = typer.Option(..., "--annotation-import-id"),
    display_name: str = typer.Option(..., "--display-name"),
    version: str = typer.Option(...),
    task: Path = typer.Option(..., exists=True, dir_okay=False),
    system: Path = typer.Option(..., exists=True, dir_okay=False),
) -> None:
    storage_root, registry = _context(system)
    task_config = _register_task(task, registry)
    result = release_dataset(
        task_config,
        annotation_import_id,
        version,
        storage_root,
        registry,
        DvcAdapter(storage_root),
        display_name=display_name,
    )
    typer.echo(f"{result.release_id} {result.release_path}")


if __name__ == "__main__":
    app()
