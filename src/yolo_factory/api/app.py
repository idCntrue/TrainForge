import os
import json
import shutil
import uuid
import hashlib
import threading
import yaml
from dataclasses import asdict
from functools import wraps
from pathlib import Path
from datetime import datetime

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from sqlalchemy import delete, func, select

from yolo_factory.api.jobs import job_tracker, JobStatus
from yolo_factory.api.task_metadata import decode_task_classes, encode_task_classes
from yolo_factory.api.queries import (
    dashboard_summary,
    list_dataset_releases,
    list_tasks,
    list_video_collections,
    registered_video_path,
)
from yolo_factory.api.schemas import (
    DashboardSummary,
    DatasetReleaseSummary,
    DatasetReconciliationFindingResponse,
    DatasetReconciliationRegisterRequest,
    TaskSummary,
    TaskCreateRequest,
    TaskUpdateRequest,
    VideoCollectionSummary,
    VideoImportRequest,
    FrameExtractRequest,
    FrameAssetSummary,
    FramePageResponse,
    FrameStatusCounts,
    BulkFrameSelectionRequest,
    FrameTrashRequest,
    RecycleMutationRequest,
    RecyclePurgeRequest,
    SamPreviewRequest,
    DuplicateGroupSummary,
    SelectionUpdateRequest,
    AnnotationImportRequest,
    DatasetReleaseRequest,
    TrainingRunCreateRequest,
    TrainingRetryRequest,
    TrainingRunResponse,
    ModelVersionCreateRequest,
    ModelVersionResponse,
    ModelGateReportResponse,
    ModelGateRunResponse,
    ModelGateRunDeleteResponse,
    ImportedModelResponse,
    InferenceRunCreateRequest,
    InferenceRunResponse,
    AnnotationSyncRequest,
    AnnotationShapeMutationRequest,
    AnnotationStatusRequest,
    AnnotationImageResponse,
    AnnotationImagePageResponse,
    AnnotationSyncResponse,
    NativeAnnotationExportRequest,
    SamSuggestionRequest,
)
from yolo_factory.config.loader import load_system_config, load_task_config
from yolo_factory.config.models import TaskConfig
from yolo_factory.registry.database import create_registry, session_scope
from yolo_factory.registry.models import AnnotationExport, AnnotationImageRecord, AnnotationShapeRecord, DatasetRelease, InferenceRunRecord, ModelVersionRecord, Task, TrainingRunRecord, VideoCollection, VideoAsset, FrameBatch, FrameAsset
from yolo_factory.training.executor import ActiveTrainingRunError, LocalTrainingExecutor
from yolo_factory.training.models import TrainingRun, TrainingRunSpec
from yolo_factory.training.repository import ActiveTrainingRunDeletion, InvalidTrainingTransition, ReferencedTrainingRunDeletion, TrainingRunRepository
from yolo_factory.training.details import build_training_details
from yolo_factory.training.resource_policy import (
    InsufficientTrainingMemory,
    InsufficientTrainingStorage,
    TrainingResourcePolicy,
    UnsafeTrainingConfiguration,
)
from yolo_factory.training.resource_snapshot import read_training_memory_snapshot
from yolo_factory.training.resource_cleanup import cleanup_training_resources
from yolo_factory.training.storage_cleanup import cleanup_training_storage
from yolo_factory.training.recovery import plan_safe_retry
from yolo_factory.training.presets import resolve_training_preset
from yolo_factory.datasets.quality import analyze_dataset_quality
from yolo_factory.datasets.reconciliation import DatasetReconciliationError, register_orphan_release, scan_dataset_releases
from yolo_factory.models.domain import ModelVersionSpec
from yolo_factory.models.executor import LocalModelGateExecutor, ModelGateError
from yolo_factory.models.repository import DuplicateModelRegistration, InvalidModelTransition, ModelVersionRepository, PublishedModelDeletion, ReferencedModelDeletion
from yolo_factory.models.release_bundle import ReleaseBundleError, build_release_bundle
from yolo_factory.models.gates import file_metadata
from yolo_factory.models.gate_history import gate_run_directory, list_gate_runs, read_gate_run_result
from yolo_factory.models.imported_inspector import inspect_imported_model
from yolo_factory.models.imported_repository import ImportedModelRepository, ReferencedImportedModelDeletion
from yolo_factory.inference.executor import InferenceExecutionError, LocalInferenceExecutor
from yolo_factory.inference.repository import ActiveInferenceRunDeletion, InferenceRunRepository
from yolo_factory.common.operation_guard import ActiveHeavyOperationError, HeavyOperationGuard
from yolo_factory.video.import_service import VIDEO_EXTENSIONS, import_video_collection
from yolo_factory.frames.extractor import extract_interval_frames
from yolo_factory.frames.video_append import append_videos_to_batch
from yolo_factory.frames.deduplication import find_duplicate_groups
from yolo_factory.frames.selection import sync_selection
from yolo_factory.frames.recycle_bin import FrameRecycleBin
from yolo_factory.storage.objects import LocalObjectStorage
from yolo_factory.annotations.package_service import build_roboflow_package
from yolo_factory.annotations.exporter import export_reviewed_annotations
from yolo_factory.annotations.geometry import GeometryError
from yolo_factory.annotations.repository import AnnotationConflict, AnnotationRepository, AnnotationSourceUnavailable, InvalidAnnotationTransition
from yolo_factory.annotations.sam_executor import LocalSamExecutor, SamExecutionError

project_root = Path(__file__).resolve().parents[3]


def _default_storage_root() -> Path:
    config_path = Path(
        os.environ.get("YOLO_FACTORY_SYSTEM_CONFIG", "configs/system.yaml")
    )
    return load_system_config(config_path).storage_root


def _cors_allowed_origins(environment=os.environ) -> list[str]:
    return [
        origin.strip()
        for origin in environment.get("CORS_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]


def _upload_byte_limit(environment=os.environ) -> int:
    raw = environment.get("YOLO_FACTORY_MAX_UPLOAD_BYTES", str(2 * 1024**3))
    try:
        limit = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("YOLO_FACTORY_MAX_UPLOAD_BYTES must be a positive integer") from exc
    if limit <= 0:
        raise ValueError("YOLO_FACTORY_MAX_UPLOAD_BYTES must be a positive integer")
    return limit


def bg_video_import(job_id: str, args: dict):
    task_id = args["task_id"]
    collection_id = args["collection_id"]
    source_dir = Path(args["source_dir"])
    storage_root = args["storage_root"]
    registry = args["registry"]
    task_config = args["task_config"]

    # Register task first
    with session_scope(registry) as session:
        existing = session.get(Task, task_id)
        classes_json = json.dumps(task_config.classes, ensure_ascii=False)
        if existing is None:
            session.add(Task(
                id=task_id,
                task_type=task_config.task_type,
                annotation_format=task_config.annotation_format,
                classes_json=classes_json
            ))

    try:
        import_video_collection(task_id, collection_id, source_dir, storage_root, registry)
    finally:
        if args.get("cleanup_source"):
            shutil.rmtree(source_dir, ignore_errors=True)


def bg_frame_extract(job_id: str, args: dict):
    collection_id = args["collection_id"]
    batch_id = args["batch_id"]
    interval = args["interval"]
    quality = args["quality"]
    storage_root = args["storage_root"]
    registry = args["registry"]
    task_id = args["task_id"]

    with session_scope(registry) as session:
        videos = list(session.execute(
            select(VideoAsset.id, VideoAsset.stored_path, VideoAsset.sha256)
            .where(VideoAsset.collection_id == collection_id)
        ).all())

    if not videos:
        raise ValueError(f"no videos in collection: {collection_id}")

    batch_dir = storage_root / "frame-batches" / task_id / batch_id
    candidates_dir = batch_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    with session_scope(registry) as session:
        existing = session.get(FrameBatch, batch_id)
        if existing is None:
            session.add(FrameBatch(
                id=batch_id,
                collection_id=collection_id,
                manifest_path=(batch_dir / "manifest.yaml").relative_to(storage_root).as_posix()
            ))

    total = len(videos)
    all_frames = []
    sha256_to_db_id = {sha256: video_db_id for video_db_id, _, sha256 in videos}

    for idx, (video_db_id, stored_path, sha256) in enumerate(videos):
        full_video_path = storage_root / stored_path
        job_tracker.update_job(
            job_id,
            progress=round((idx / total) * 90.0, 1),
            message=f"正在抽帧视频 ({idx + 1}/{total}): {full_video_path.name}"
        )

        frames = extract_interval_frames(
            full_video_path,
            candidates_dir,
            collection_id,
            video_db_id,
            interval,
            quality
        )
        all_frames.extend(frames)

    job_tracker.update_job(job_id, progress=90.0, message="正在注册帧文件到数据库...")

    with session_scope(registry) as session:
        for f_idx, frame in enumerate(all_frames):
            frame_id = f"frame-{batch_id}-{frame.sha256[:16]}-{f_idx}"
            existing = session.get(FrameAsset, frame_id)
            video_db_id = sha256_to_db_id.get(frame.source_video_sha256)
            if existing is None and video_db_id is not None:
                storage_key = frame.path.resolve().relative_to(storage_root.resolve()).as_posix()
                session.add(FrameAsset(
                    id=frame_id,
                    batch_id=batch_id,
                    video_id=video_db_id,
                    stored_path=storage_key,
                    sha256=frame.sha256,
                    timestamp_ms=frame.timestamp_ms,
                    frame_index=frame.frame_index,
                    status="candidate",
                    storage_key=storage_key,
                    size_bytes=frame.path.stat().st_size,
                ))


def bg_append_batch_videos(job_id: str, args: dict):
    source_dir = Path(args["source_dir"])
    try:
        result = append_videos_to_batch(
            args["batch_id"],
            source_dir,
            args["storage_root"],
            args["registry"],
            interval=args["interval"],
            quality=args["quality"],
        )
        payload = asdict(result)
        job_tracker.update_job(
            job_id,
            progress=95.0,
            message=(
                f"已追加 {result.imported_video_count} 个视频、"
                f"{result.created_frame_count} 张待筛选图片"
            ),
            payload=payload,
        )
    finally:
        shutil.rmtree(source_dir, ignore_errors=True)


def _training_response(run: TrainingRun) -> TrainingRunResponse:
    return TrainingRunResponse(
        id=run.id,
        name=run.spec.name,
        task_type=run.spec.task_type,
        dataset_release_id=run.spec.dataset_release_id,
        base_model=run.spec.base_model,
        epochs=run.spec.epochs,
        batch=run.spec.batch,
        image_size=run.spec.image_size,
        device=run.spec.device,
        status=run.status,
        progress=run.progress,
        phase=run.phase,
        message=run.message,
        pid=run.pid,
        run_directory=run.run_directory,
        created_at=run.created_at,
        updated_at=run.updated_at,
        finished_at=run.finished_at,
        exit_code=run.exit_code,
        selected_classes=list(run.spec.selected_classes),
        class_aliases=run.spec.class_aliases,
        epoch=run.epoch,
        total_epochs=run.total_epochs,
        metrics=run.metrics,
        artifacts=run.artifacts,
        source_run_id=run.spec.source_run_id,
        execution_mode=run.spec.execution_mode,
        retry_strategy=run.spec.retry_strategy,
        preset_id=run.spec.preset_id,
        patience=run.spec.patience,
        optimizer=run.spec.optimizer,
        close_mosaic=run.spec.close_mosaic,
        augment_profile=run.spec.augment_profile,
        augmentation=run.spec.augmentation,
    )


def _artifact_response(path_value: str) -> dict:
    path = Path(path_value).resolve()
    if not path.is_file():
        return {"path": str(path), "exists": False, "size_bytes": 0, "sha256": ""}
    return {**file_metadata(path), "exists": True}


def _model_response(model) -> ModelVersionResponse:
    artifacts = {key: dict(value) for key, value in model.artifacts.items()}
    artifacts.setdefault("pt", _artifact_response(model.spec.pt_path))
    for key, artifact in artifacts.items():
        path_value = artifact.get("path") if isinstance(artifact, dict) else None
        if path_value:
            artifacts[key] = {**artifact, **_artifact_response(path_value)}
    return ModelVersionResponse(
        id=model.id,
        name=model.spec.name,
        version=model.spec.version,
        task_type=model.spec.task_type,
        training_run_id=model.spec.training_run_id,
        dataset_release_id=model.spec.dataset_release_id,
        selected_classes=list(model.spec.selected_classes),
        class_aliases=model.spec.class_aliases,
        metrics=model.spec.metrics,
        status=model.status,
        gates=model.gates,
        artifacts=artifacts,
        environment=model.environment,
        gate_report_path=model.gate_report_path,
        quality_report=model.spec.quality_report,
        created_at=model.created_at,
        updated_at=model.updated_at,
        published_at=model.published_at,
        archived_at=model.archived_at,
    )


def _inference_response(run: dict) -> InferenceRunResponse:
    result = None
    if run["result_path"]:
        result_path = Path(run["result_path"])
        if result_path.is_file():
            result = json.loads(result_path.read_text(encoding="utf-8"))
    return InferenceRunResponse(**run, result=result)


def _imported_model_response(model) -> ImportedModelResponse:
    return ImportedModelResponse(
        id=model.id, name=model.name, task_type=model.task_type,
        artifact_format=model.artifact_format, original_name=model.original_name,
        artifact=_artifact_response(model.artifact_path), status=model.status,
        class_names=list(model.class_names), created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _annotation_response(image) -> AnnotationImageResponse:
    return AnnotationImageResponse(
        frame_id=image.frame_id, task_id=image.task_id, task_type=image.task_type,
        image_path=image.image_path, width=image.width, height=image.height,
        status=image.status, revision=image.revision, classes=list(image.classes),
        shapes=[{"id": shape.id, "class_id": shape.class_id, "class_name": shape.class_name, "shape_type": shape.shape_type, "coordinates": list(shape.coordinates), "source": shape.source, "created_at": shape.created_at, "updated_at": shape.updated_at} for shape in image.shapes],
        created_at=image.created_at, updated_at=image.updated_at,
    )


def create_app(
    storage_root: Path | None = None,
    *,
    task_config_dir: Path | None = None,
    training_engine: str = "ultralytics",
    training_step_seconds: float = 0.15,
    model_gate_executor=None,
    inference_executor=None,
    sam_executor=None,
    training_resource_policy: TrainingResourcePolicy | None = None,
    training_disk_usage=shutil.disk_usage,
    training_storage_cleanup=cleanup_training_storage,
    training_memory_snapshot=read_training_memory_snapshot,
    training_resource_cleanup=cleanup_training_resources,
    imported_model_inspector=inspect_imported_model,
) -> FastAPI:
    root = (storage_root or _default_storage_root()).resolve()
    max_upload_bytes = _upload_byte_limit()
    default_task_configs = Path(
        os.environ.get("YOLO_FACTORY_TASK_CONFIG_DIR", project_root / "configs" / "tasks")
    )
    task_configs = (task_config_dir or default_task_configs).resolve()
    registry = create_registry(root / "registry" / "factory.db")
    app = FastAPI(title="YOLO Model Factory", version="0.1.1")
    app.state.storage_root = root
    app.state.registry = registry
    object_storage = LocalObjectStorage(root)
    recycle_bin = FrameRecycleBin(registry, object_storage, operations_root=root / "recycle-bin" / "operations")
    app.state.recycle_bin = recycle_bin
    recycle_stop = threading.Event()
    recycle_thread: threading.Thread | None = None

    def recycle_cleanup_loop() -> None:
        while not recycle_stop.is_set():
            try:
                recycle_bin.purge_expired(limit=100)
            except Exception:
                pass
            recycle_stop.wait(24 * 60 * 60)

    @app.on_event("startup")
    def start_recycle_cleanup() -> None:
        nonlocal recycle_thread
        if recycle_thread is None or not recycle_thread.is_alive():
            recycle_stop.clear()
            recycle_thread = threading.Thread(target=recycle_cleanup_loop, name="frame-recycle-cleanup", daemon=True)
            recycle_thread.start()

    @app.on_event("shutdown")
    def stop_recycle_cleanup() -> None:
        recycle_stop.set()
        if recycle_thread is not None:
            recycle_thread.join(timeout=2)
    training_repository = TrainingRunRepository(registry)
    resource_policy = training_resource_policy or TrainingResourcePolicy.from_environment(os.environ)
    training_executor = LocalTrainingExecutor(
        training_repository,
        root,
        engine=training_engine,
        simulation_step_seconds=training_step_seconds,
        resource_policy=resource_policy,
    )
    training_executor.recover_stale_runs()
    app.state.training_repository = training_repository
    app.state.training_executor = training_executor

    def prepare_training_storage() -> None:
        try:
            app.state.last_training_cleanup = training_storage_cleanup(root)
        except Exception as exc:
            app.state.last_training_cleanup = {"errors": (str(exc),)}
        resource_policy.validate_free_disk(root, usage=training_disk_usage)
        if training_engine == "ultralytics":
            resource_policy.validate_memory_snapshot(training_memory_snapshot())
    model_repository = ModelVersionRepository(registry)
    imported_model_repository = ImportedModelRepository(registry)
    gate_executor = model_gate_executor or LocalModelGateExecutor(root)
    app.state.model_repository = model_repository
    app.state.imported_model_repository = imported_model_repository
    app.state.model_gate_executor = gate_executor
    inference_repository = InferenceRunRepository(registry)
    local_inference_executor = inference_executor or LocalInferenceExecutor(inference_repository, root)
    if hasattr(local_inference_executor, "recover_stale_runs"):
        local_inference_executor.recover_stale_runs()
    app.state.inference_repository = inference_repository
    app.state.inference_executor = local_inference_executor
    annotation_repository = AnnotationRepository(registry, object_storage)
    app.state.annotation_repository = annotation_repository
    local_sam_executor = sam_executor or LocalSamExecutor(root)
    app.state.sam_executor = local_sam_executor

    async def save_uploaded_file(upload: UploadFile, destination: Path) -> int:
        destination.parent.mkdir(parents=True, exist_ok=True)
        bytes_written = 0
        try:
            with destination.open("xb") as stream:
                while chunk := await upload.read(1024 * 1024):
                    if bytes_written + len(chunk) > max_upload_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"upload exceeds configured {max_upload_bytes} byte limit",
                        )
                    stream.write(chunk)
                    bytes_written += len(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await upload.close()
        return bytes_written

    def safe_upload_name(upload: UploadFile, allowed_extensions: set[str], kind: str) -> str:
        raw_name = upload.filename or ""
        normalized = raw_name.replace("\\", "/")
        filename = Path(normalized).name
        if not filename or filename != normalized:
            raise HTTPException(status_code=422, detail=f"{kind} filename must not contain a path")
        if Path(filename).suffix.lower() not in allowed_extensions:
            raise HTTPException(status_code=422, detail=f"unsupported {kind} extension: {filename}")
        return filename

    def require_path_within(candidate: Path, parent: Path, detail: str) -> Path:
        resolved = candidate.expanduser().resolve()
        try:
            resolved.relative_to(parent.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=403, detail=detail) from exc
        return resolved

    def resolve_task_config(task_id: str) -> TaskConfig | None:
        preferred = task_configs / f"{task_id}.yaml"
        candidates = [preferred] if preferred.is_file() else []
        candidates.extend(path for path in task_configs.glob("*.yaml") if path != preferred)
        for path in candidates:
            config = load_task_config(path)
            if config.task_id == task_id:
                return config

        with session_scope(registry) as session:
            task = session.get(Task, task_id)
            if task is None:
                return None
            classes, display_names = decode_task_classes(task.classes_json)
            return TaskConfig(
                task_id=task.id,
                task_type=task.task_type,
                classes=classes,
                class_display_names=display_names,
                annotation_format=task.annotation_format,
            )

    def managed_uploaded_weight_directories(session, training_records: list[TrainingRunRecord]) -> list[Path]:
        upload_root = (root / "model-weights" / "uploads").resolve()
        deleting_ids = {record.id for record in training_records}
        candidates: set[Path] = set()
        for record in training_records:
            weight_path = Path(record.base_model).resolve()
            try:
                weight_path.relative_to(upload_root)
            except ValueError:
                continue
            candidates.add(weight_path.parent)
        if not candidates:
            return []

        retained_records = list(session.scalars(
            select(TrainingRunRecord).where(TrainingRunRecord.id.not_in(deleting_ids))
        )) if deleting_ids else list(session.scalars(select(TrainingRunRecord)))
        retained_directories = {Path(record.base_model).resolve().parent for record in retained_records}
        return sorted(candidates - retained_directories)

    def delete_downstream_records(session, model_ids: list[str], *, delete_artifacts: bool) -> list[Path]:
        if not model_ids:
            return []
        inference_records = list(session.scalars(select(InferenceRunRecord).where(InferenceRunRecord.model_version_id.in_(model_ids))))
        active_inference = next((record.id for record in inference_records if record.status in {"queued", "running"}), None)
        if active_inference is not None:
            raise HTTPException(status_code=409, detail=f"active inference run {active_inference} prevents cascade deletion")
        artifact_paths: list[Path] = []
        if delete_artifacts:
            for record in inference_records:
                if record.output_directory:
                    artifact_paths.append(Path(record.output_directory).resolve())
            for model in session.scalars(select(ModelVersionRecord).where(ModelVersionRecord.id.in_(model_ids))):
                config = json.loads(model.config_json)
                shared_pt = config.get("pt_path", "")
                if shared_pt:
                    validate_artifact_paths([Path(shared_pt).resolve()])
                candidates = [
                    item.get("path", "")
                    for name, item in config.get("artifacts", {}).items()
                    if name != "pt"
                ]
                artifact_paths.extend(Path(value).resolve() for value in candidates if value)
            validate_artifact_paths(artifact_paths)
        session.execute(delete(InferenceRunRecord).where(InferenceRunRecord.model_version_id.in_(model_ids)))
        session.execute(delete(ModelVersionRecord).where(ModelVersionRecord.id.in_(model_ids)))
        return artifact_paths

    def validate_artifact_paths(paths: list[Path]) -> None:
        storage_root = root.resolve()
        for path in paths:
            try:
                path.relative_to(storage_root)
            except ValueError as exc:
                raise HTTPException(status_code=409, detail="cascade artifacts are outside storage root") from exc

    def remove_artifact_paths(paths: list[Path]) -> None:
        for path in sorted(set(paths), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
    heavy_operation_guard = HeavyOperationGuard()
    app.state.heavy_operation_guard = heavy_operation_guard

    def heavy_operation(name: str):
        def decorate(function):
            @wraps(function)
            def guarded(*args, **kwargs):
                try:
                    with heavy_operation_guard.acquire(name):
                        return function(*args, **kwargs)
                except ActiveHeavyOperationError as exc:
                    raise HTTPException(status_code=409, detail=str(exc)) from exc
            return guarded
        return decorate
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_allowed_origins(),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "storage_root": str(root)}

    @app.post("/api/training-resources/cleanup")
    @heavy_operation("training-resource-cleanup")
    def cleanup_training_resource_cache() -> dict:
        active_statuses = {"queued", "running", "evaluating", "exporting", "verifying"}
        active_run = next(
            (run for run in training_repository.list() if run.status in active_statuses),
            None,
        )
        if active_run is not None:
            raise HTTPException(
                status_code=409,
                detail=f"training run {active_run.id} is active; wait or cancel it before cleanup",
            )
        active_inference = next(
            (run for run in inference_repository.list() if run["status"] in {"queued", "running"}),
            None,
        )
        if active_inference is not None:
            raise HTTPException(
                status_code=409,
                detail=f"inference run {active_inference['id']} is active; wait or cancel it before cleanup",
            )
        return training_resource_cleanup(root).model_dump()

    @app.get("/api/dashboard", response_model=DashboardSummary)
    def dashboard() -> DashboardSummary:
        return dashboard_summary(registry)

    @app.get("/api/tasks", response_model=list[TaskSummary])
    def tasks() -> list[TaskSummary]:
        return list_tasks(registry)

    @app.post("/api/tasks", response_model=TaskSummary, status_code=201)
    def create_task(req: TaskCreateRequest) -> TaskSummary:
        config_path = task_configs / f"{req.id}.yaml"
        with session_scope(registry) as session:
            if session.get(Task, req.id) is not None or config_path.exists():
                raise HTTPException(status_code=409, detail="task id already exists")
            annotation_format = "yolo-detect" if req.task_type == "detect" else "yolo-seg"
            task_configs.mkdir(parents=True, exist_ok=True)
            temporary_path = config_path.with_suffix(".yaml.tmp")
            temporary_path.write_text(yaml.safe_dump({
                "task_id": req.id,
                "task_type": req.task_type,
                "classes": req.classes,
                "class_display_names": req.class_display_names,
                "annotation_format": annotation_format,
            }, allow_unicode=True, sort_keys=False), encoding="utf-8")
            temporary_path.replace(config_path)
            task = Task(id=req.id, task_type=req.task_type, annotation_format=annotation_format, classes_json=encode_task_classes(req.classes, req.class_display_names))
            session.add(task)
            session.flush()
            session.refresh(task)
            return TaskSummary(id=task.id, task_type=task.task_type, annotation_format=task.annotation_format, classes=req.classes, class_display_names=req.class_display_names, created_at=task.created_at)

    @app.patch("/api/tasks/{task_id}", response_model=TaskSummary)
    def update_task(task_id: str, req: TaskUpdateRequest) -> TaskSummary:
        config_path = task_configs / f"{task_id}.yaml"
        with session_scope(registry) as session:
            task = session.get(Task, task_id)
            if task is None:
                raise HTTPException(status_code=404, detail="task not found")
            classes, _ = decode_task_classes(task.classes_json)
            unknown = set(req.class_display_names) - set(classes)
            if unknown:
                raise HTTPException(status_code=422, detail="class display names must target declared classes")
            task.classes_json = encode_task_classes(classes, req.class_display_names)
            task_configs.mkdir(parents=True, exist_ok=True)
            temporary_path = config_path.with_suffix(".yaml.tmp")
            temporary_path.write_text(yaml.safe_dump({
                "task_id": task.id,
                "task_type": task.task_type,
                "classes": classes,
                "class_display_names": req.class_display_names,
                "annotation_format": task.annotation_format,
            }, allow_unicode=True, sort_keys=False), encoding="utf-8")
            temporary_path.replace(config_path)
            session.flush()
            session.refresh(task)
            return TaskSummary(
                id=task.id,
                task_type=task.task_type,
                annotation_format=task.annotation_format,
                classes=classes,
                class_display_names=req.class_display_names,
                created_at=task.created_at,
            )

    @app.delete("/api/tasks/{task_id}", status_code=204)
    def delete_task(task_id: str, delete_artifacts: bool = False, cascade: bool = False) -> Response:
        artifact_paths: list[Path] = []
        config_path = task_configs / f"{task_id}.yaml"
        with session_scope(registry) as session:
            task = session.get(Task, task_id)
            if task is None:
                raise HTTPException(status_code=404, detail="task not found")

            collection_ids = list(session.scalars(select(VideoCollection.id).where(VideoCollection.task_id == task_id)))
            annotation_frame_ids = list(session.scalars(select(AnnotationImageRecord.frame_id).where(AnnotationImageRecord.task_id == task_id)))
            export_ids = list(session.scalars(select(AnnotationExport.id).where(AnnotationExport.task_id == task_id)))
            release_ids = list(session.scalars(select(DatasetRelease.id).where(DatasetRelease.task_id == task_id)))
            dependencies = collection_ids or annotation_frame_ids or export_ids or release_ids
            if dependencies and not cascade:
                raise HTTPException(status_code=409, detail=f"task is referenced by resource {dependencies[0]}; use cascade deletion")

            if cascade:
                collections = list(session.scalars(select(VideoCollection).where(VideoCollection.task_id == task_id)))
                batches = list(session.scalars(select(FrameBatch).where(FrameBatch.collection_id.in_(collection_ids)))) if collection_ids else []
                batch_ids = [batch.id for batch in batches]
                video_assets = list(session.scalars(select(VideoAsset).where(VideoAsset.collection_id.in_(collection_ids)))) if collection_ids else []
                frame_ids = list(session.scalars(select(FrameAsset.id).where(FrameAsset.batch_id.in_(batch_ids)))) if batch_ids else []
                exports = list(session.scalars(select(AnnotationExport).where(AnnotationExport.task_id == task_id)))
                releases = list(session.scalars(select(DatasetRelease).where(DatasetRelease.task_id == task_id)))
                training_records = list(session.scalars(select(TrainingRunRecord).where(TrainingRunRecord.dataset_release_id.in_(release_ids)))) if release_ids else []
                active_training = next((record.id for record in training_records if record.status in {"queued", "running", "evaluating", "exporting", "verifying"}), None)
                if active_training is not None:
                    raise HTTPException(status_code=409, detail=f"active training run {active_training} prevents cascade deletion")
                training_ids = [record.id for record in training_records]
                model_ids = list(session.scalars(select(ModelVersionRecord.id).where(ModelVersionRecord.dataset_release_id.in_(release_ids)))) if release_ids else []

                if delete_artifacts:
                    artifact_paths.extend((root / asset.stored_path).resolve() for asset in video_assets)
                    artifact_paths.extend((root / batch.manifest_path).resolve().parent for batch in batches)
                    artifact_paths.extend((root / export.zip_path).resolve() for export in exports)
                    artifact_paths.extend((root / release.release_path).resolve() for release in releases)
                    artifact_paths.extend(Path(record.run_directory).resolve() for record in training_records if record.run_directory)
                    artifact_paths.extend(managed_uploaded_weight_directories(session, training_records))
                    validate_artifact_paths(artifact_paths)

                artifact_paths.extend(delete_downstream_records(session, model_ids, delete_artifacts=delete_artifacts))
                if training_ids:
                    session.execute(delete(TrainingRunRecord).where(TrainingRunRecord.id.in_(training_ids)))
                if release_ids:
                    session.execute(delete(DatasetRelease).where(DatasetRelease.id.in_(release_ids)))
                if export_ids:
                    session.execute(delete(AnnotationExport).where(AnnotationExport.id.in_(export_ids)))
                all_annotation_frame_ids = list(dict.fromkeys([*annotation_frame_ids, *frame_ids]))
                if all_annotation_frame_ids:
                    session.execute(delete(AnnotationShapeRecord).where(AnnotationShapeRecord.frame_id.in_(all_annotation_frame_ids)))
                    session.execute(delete(AnnotationImageRecord).where(AnnotationImageRecord.frame_id.in_(all_annotation_frame_ids)))
                if frame_ids:
                    session.execute(delete(FrameAsset).where(FrameAsset.id.in_(frame_ids)))
                if batch_ids:
                    session.execute(delete(FrameBatch).where(FrameBatch.id.in_(batch_ids)))
                if collection_ids:
                    session.execute(delete(VideoAsset).where(VideoAsset.collection_id.in_(collection_ids)))
                    session.execute(delete(VideoCollection).where(VideoCollection.id.in_(collection_ids)))

            session.delete(task)

        validate_artifact_paths(artifact_paths)
        remove_artifact_paths(artifact_paths)
        if config_path.is_file():
            config_path.unlink()
        return Response(status_code=204)

    @app.get(
        "/api/video-collections",
        response_model=list[VideoCollectionSummary],
    )
    def video_collections() -> list[VideoCollectionSummary]:
        return list_video_collections(registry)

    @app.get(
        "/api/dataset-releases",
        response_model=list[DatasetReleaseSummary],
    )
    def dataset_releases() -> list[DatasetReleaseSummary]:
        return list_dataset_releases(registry, root)

    @app.get(
        "/api/dataset-releases/reconciliation",
        response_model=list[DatasetReconciliationFindingResponse],
    )
    def dataset_release_reconciliation() -> list[DatasetReconciliationFindingResponse]:
        return [DatasetReconciliationFindingResponse(**finding.to_dict()) for finding in scan_dataset_releases(registry, root)]

    @app.post(
        "/api/dataset-releases/reconciliation/register",
        response_model=DatasetReleaseSummary,
        status_code=201,
    )
    def register_reconciled_dataset_release(req: DatasetReconciliationRegisterRequest) -> DatasetReleaseSummary:
        try:
            release = register_orphan_release(registry, root, req.release_path)
        except DatasetReconciliationError as exc:
            detail = str(exc)
            status_code = 422 if "outside" in detail or "symbolic" in detail else 409
            raise HTTPException(status_code=status_code, detail=detail) from exc
        return next(item for item in list_dataset_releases(registry, root) if item.id == release.id)

    @app.get("/api/dataset-releases/{release_id}/quality")
    def dataset_release_quality(release_id: str) -> dict:
        with session_scope(registry) as session:
            release = session.get(DatasetRelease, release_id)
            if release is None or release.status != "published":
                raise HTTPException(status_code=404, detail="published dataset release not found")
            task = session.get(Task, release.task_id)
            if task is None:
                raise HTTPException(status_code=409, detail="dataset task is missing")
            class_names, _ = decode_task_classes(task.classes_json)
            release_path = (root / release.release_path).resolve()
        return analyze_dataset_quality(release_path, class_names=class_names).model_dump()

    def start_training_run(req: TrainingRunCreateRequest) -> TrainingRunResponse:
        if req.preset_id != "custom":
            try:
                preset = resolve_training_preset(req.preset_id, task_type=req.task_type, device=req.device)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            req = req.model_copy(update=preset.model_dump())
        if any(run.status in {"running", "evaluating", "exporting", "verifying"} for run in training_repository.list()):
            raise HTTPException(status_code=409, detail="another training run is active")
        if any(run["status"] in {"queued", "running"} for run in inference_repository.list()):
            raise HTTPException(status_code=409, detail="another GPU operation is active")
        with session_scope(registry) as session:
            release = session.get(DatasetRelease, req.dataset_release_id)
            if release is None or release.status != "published":
                raise HTTPException(status_code=404, detail="published dataset release not found")
            task = session.get(Task, release.task_id)
            if task is None:
                raise HTTPException(status_code=409, detail="dataset task is missing")
            if task.task_type != req.task_type:
                raise HTTPException(status_code=409, detail="training task does not match dataset release")
            task_classes, _ = decode_task_classes(task.classes_json)
            selected_classes = req.selected_classes or task_classes
            if not selected_classes or any(class_name not in task_classes for class_name in selected_classes):
                raise HTTPException(status_code=409, detail="selected classes must exist in the dataset task")
            class_aliases = {name: alias.strip() for name, alias in req.class_aliases.items() if alias.strip()}
            if any(class_name not in selected_classes for class_name in class_aliases):
                raise HTTPException(status_code=409, detail="class aliases must target selected classes")
            release_path = (root / release.release_path).resolve()
            data_yaml_path = release_path / "data.yaml"
            if not data_yaml_path.is_file():
                raise HTTPException(status_code=409, detail="dataset release data.yaml is missing")
            quality_report = analyze_dataset_quality(release_path, class_names=task_classes)
            if quality_report.blockers:
                raise HTTPException(
                    status_code=409,
                    detail="dataset quality blockers: " + ", ".join(quality_report.blockers),
                )
        try:
            resource_policy.validate_request(
                req.task_type,
                req.device,
                batch=req.batch,
                image_size=req.image_size,
            )
            prepare_training_storage()
        except UnsafeTrainingConfiguration as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except InsufficientTrainingStorage as exc:
            raise HTTPException(status_code=409, detail=exc.as_detail()) from exc
        except InsufficientTrainingMemory as exc:
            raise HTTPException(status_code=409, detail=exc.as_detail()) from exc
        run = training_repository.create(
            TrainingRunSpec(
                name=req.name,
                task_type=req.task_type,
                dataset_release_id=req.dataset_release_id,
                base_model=req.base_model,
                epochs=req.epochs,
                batch=req.batch,
                image_size=req.image_size,
                device=req.device,
                selected_classes=tuple(selected_classes),
                class_aliases=class_aliases,
                preset_id=req.preset_id,
                patience=req.patience,
                optimizer=req.optimizer,
                close_mosaic=req.close_mosaic,
                augment_profile=req.augment_profile,
                augmentation=req.augmentation.model_dump() if hasattr(req.augmentation, "model_dump") else dict(req.augmentation),
            ),
            run_id=f"training-{uuid.uuid4().hex}",
        )
        try:
            run = training_executor.start(
                run.id,
                dataset_release_path=release_path,
                data_yaml_path=data_yaml_path,
            )
        except ActiveTrainingRunError as exc:
            raise HTTPException(status_code=409, detail="another training run is active") from exc
        return _training_response(run)

    @app.post(
        "/api/training-runs",
        response_model=TrainingRunResponse,
        status_code=201,
    )
    @heavy_operation("training-start")
    def create_training_run(req: TrainingRunCreateRequest) -> TrainingRunResponse:
        base_model_path = Path(req.base_model).expanduser()
        if base_model_path.parent != Path("."):
            allowed_roots = [root / "model-weights"]
            configured_model_dir = os.environ.get("YOLO_FACTORY_MODEL_DIR")
            if configured_model_dir:
                allowed_roots.append(Path(configured_model_dir))
            resolved = base_model_path.resolve()
            if not any(resolved == allowed.resolve() or resolved.is_relative_to(allowed.resolve()) for allowed in allowed_roots):
                raise HTTPException(status_code=403, detail="base model path is outside managed model directories")
            req = req.model_copy(update={"base_model": str(resolved)})
        return start_training_run(req)

    @app.post(
        "/api/training-runs/upload",
        response_model=TrainingRunResponse,
        status_code=201,
    )
    async def create_training_run_with_weight(
        name: str = Form(...),
        task_type: str = Form(...),
        dataset_release_id: str = Form(...),
        epochs: int = Form(...),
        batch: int = Form(...),
        image_size: int = Form(...),
        device: str = Form(...),
        selected_classes: str = Form("[]"),
        class_aliases: str = Form("{}"),
        preset_id: str = Form("custom"),
        patience: int = Form(20),
        optimizer: str = Form("auto"),
        close_mosaic: int = Form(10),
        augment_profile: str = Form("standard"),
        augmentation: str = Form("{}"),
        base_model_file: UploadFile = File(...),
    ) -> TrainingRunResponse:
        filename = safe_upload_name(base_model_file, {".pt"}, "model weight")
        staging_dir = root / "model-weights" / "uploads" / uuid.uuid4().hex
        destination = staging_dir / filename
        try:
            if await save_uploaded_file(base_model_file, destination) == 0:
                raise HTTPException(status_code=422, detail="model weight file is empty")
            try:
                parsed_classes = json.loads(selected_classes)
                parsed_aliases = json.loads(class_aliases)
                parsed_augmentation = json.loads(augmentation)
                if not isinstance(parsed_classes, list) or not isinstance(parsed_aliases, dict) or not isinstance(parsed_augmentation, dict):
                    raise ValueError
            except (json.JSONDecodeError, ValueError) as exc:
                raise HTTPException(status_code=422, detail="selected_classes or class_aliases is invalid JSON") from exc
            req = TrainingRunCreateRequest(
                name=name,
                task_type=task_type,
                dataset_release_id=dataset_release_id,
                base_model=str(destination.resolve()),
                epochs=epochs,
                batch=batch,
                image_size=image_size,
                device=device,
                selected_classes=parsed_classes,
                class_aliases=parsed_aliases,
                preset_id=preset_id,
                patience=patience,
                optimizer=optimizer,
                close_mosaic=close_mosaic,
                augment_profile=augment_profile,
                augmentation=parsed_augmentation,
            )
            try:
                with heavy_operation_guard.acquire("training-start"):
                    return start_training_run(req)
            except ActiveHeavyOperationError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    @app.get("/api/training-runs", response_model=list[TrainingRunResponse])
    def training_runs() -> list[TrainingRunResponse]:
        return [_training_response(run) for run in training_repository.list()]

    @app.get("/api/training-runs/{run_id}", response_model=TrainingRunResponse)
    def training_run(run_id: str) -> TrainingRunResponse:
        try:
            return _training_response(training_repository.get_required(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="training run not found") from exc

    @app.get("/api/training-runs/{run_id}/details")
    def training_run_details(run_id: str) -> dict:
        try:
            run = training_repository.get_required(run_id)
            return build_training_details(run, root, registry)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="training run not found") from exc

    @app.post("/api/training-runs/{run_id}/retry", response_model=TrainingRunResponse, status_code=201)
    def retry_training_run(run_id: str, req: TrainingRetryRequest, response: Response) -> TrainingRunResponse:
        existing = training_repository.find_retry(run_id, req.request_id)
        if existing is not None:
            response.status_code = 200
            return _training_response(existing)
        try:
            source = training_repository.get_required(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="training run not found") from exc
        if source.status != "failed":
            raise HTTPException(status_code=409, detail="only failed training runs can be retried")
        details = build_training_details(source, root, registry)
        diagnostic = details.get("failure_diagnostic") or {}
        plan = plan_safe_retry(
            task_type=source.spec.task_type,
            device=source.spec.device,
            batch=source.spec.batch,
            image_size=source.spec.image_size,
            failure_code=diagnostic.get("code", "runner_failed"),
        )
        if not plan.allowed:
            raise HTTPException(status_code=409, detail=plan.reason)
        if any(run.status in {"running", "evaluating", "exporting", "verifying"} for run in training_repository.list()):
            raise HTTPException(status_code=409, detail="another training run is active")
        try:
            resource_policy.validate_request(
                source.spec.task_type, source.spec.device,
                batch=plan.batch, image_size=plan.image_size,
            )
            prepare_training_storage()
        except UnsafeTrainingConfiguration as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except InsufficientTrainingStorage as exc:
            raise HTTPException(status_code=409, detail=exc.as_detail()) from exc
        except InsufficientTrainingMemory as exc:
            raise HTTPException(status_code=409, detail=exc.as_detail()) from exc
        with session_scope(registry) as session:
            release = session.get(DatasetRelease, source.spec.dataset_release_id)
            if release is None or release.status != "published":
                raise HTTPException(status_code=409, detail="source dataset release is no longer available")
            release_path = (root / release.release_path).resolve()
            data_yaml_path = release_path / "data.yaml"
            if not data_yaml_path.is_file():
                raise HTTPException(status_code=409, detail="source dataset data.yaml is missing")
        retry_number = len(training_repository.related(run_id)) + 1
        child = training_repository.create(
            TrainingRunSpec(
                name=f"{source.spec.name} 安全重试 {retry_number}",
                task_type=source.spec.task_type,
                dataset_release_id=source.spec.dataset_release_id,
                base_model=source.spec.base_model,
                epochs=source.spec.epochs,
                batch=plan.batch,
                image_size=plan.image_size,
                device=source.spec.device,
                selected_classes=source.spec.selected_classes,
                class_aliases=source.spec.class_aliases,
                source_run_id=source.id,
                execution_mode="train",
                retry_strategy=req.strategy,
                request_id=req.request_id,
                preset_id=plan.preset_id,
                patience=source.spec.patience,
                optimizer=source.spec.optimizer,
                close_mosaic=source.spec.close_mosaic,
                augment_profile=source.spec.augment_profile,
                augmentation=source.spec.augmentation,
            ),
            run_id=f"training-{uuid.uuid4().hex}",
        )
        child = training_executor.start(
            child.id, dataset_release_path=release_path, data_yaml_path=data_yaml_path,
        )
        return _training_response(child)

    @app.post(
        "/api/training-runs/{run_id}/recover-evaluation",
        response_model=TrainingRunResponse,
        status_code=201,
    )
    def recover_training_evaluation(run_id: str) -> TrainingRunResponse:
        try:
            source = training_repository.get_required(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="training run not found") from exc
        if source.status != "failed":
            raise HTTPException(status_code=409, detail="only failed training runs can recover evaluation")
        details = build_training_details(source, root, registry)
        recovery = details.get("recovery_options") or {}
        if not recovery.get("can_evaluate_best") or not recovery.get("best_weight_path"):
            raise HTTPException(status_code=409, detail=recovery.get("reason", "best weight cannot be evaluated"))
        if any(run.status in {"running", "evaluating", "exporting", "verifying"} for run in training_repository.list()):
            raise HTTPException(status_code=409, detail="another training run is active")
        try:
            resource_policy.validate_request(
                source.spec.task_type, source.spec.device,
                batch=source.spec.batch, image_size=source.spec.image_size,
            )
            prepare_training_storage()
        except UnsafeTrainingConfiguration as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InsufficientTrainingStorage as exc:
            raise HTTPException(status_code=409, detail=exc.as_detail()) from exc
        except InsufficientTrainingMemory as exc:
            raise HTTPException(status_code=409, detail=exc.as_detail()) from exc
        with session_scope(registry) as session:
            release = session.get(DatasetRelease, source.spec.dataset_release_id)
            if release is None or release.status != "published":
                raise HTTPException(status_code=409, detail="source dataset release is no longer available")
            release_path = (root / release.release_path).resolve()
            data_yaml_path = release_path / "data.yaml"
        best_weight = (root / recovery["best_weight_path"]).resolve()
        try:
            best_weight.relative_to(Path(source.run_directory).resolve())
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="best weight is outside the failed run directory") from exc
        recovery_number = len(training_repository.related(run_id)) + 1
        child = training_repository.create(
            TrainingRunSpec(
                name=f"{source.spec.name} 恢复评估 {recovery_number}",
                task_type=source.spec.task_type,
                dataset_release_id=source.spec.dataset_release_id,
                base_model=str(best_weight),
                epochs=source.spec.epochs,
                batch=source.spec.batch,
                image_size=source.spec.image_size,
                device=source.spec.device,
                selected_classes=source.spec.selected_classes,
                class_aliases=source.spec.class_aliases,
                source_run_id=source.id,
                execution_mode="evaluate_existing",
                preset_id=source.spec.preset_id,
                patience=source.spec.patience,
                optimizer=source.spec.optimizer,
                close_mosaic=source.spec.close_mosaic,
                augment_profile=source.spec.augment_profile,
                augmentation=source.spec.augmentation,
            ),
            run_id=f"training-{uuid.uuid4().hex}",
        )
        child = training_executor.start(
            child.id, dataset_release_path=release_path, data_yaml_path=data_yaml_path,
        )
        return _training_response(child)

    @app.post("/api/training-runs/{run_id}/refresh", response_model=TrainingRunResponse)
    def refresh_training_run(run_id: str) -> TrainingRunResponse:
        try:
            return _training_response(training_executor.refresh(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="training run not found") from exc

    @app.post("/api/training-runs/{run_id}/cancel", response_model=TrainingRunResponse)
    def cancel_training_run(run_id: str) -> TrainingRunResponse:
        try:
            return _training_response(training_executor.cancel(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="training run not found") from exc
        except InvalidTrainingTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.delete("/api/training-runs/{run_id}", status_code=204)
    def delete_training_run(run_id: str, delete_artifacts: bool = False, cascade: bool = False) -> Response:
        try:
            run = training_repository.get_required(run_id)
            uploaded_weight_directory = None
            if delete_artifacts:
                with session_scope(registry) as session:
                    record = session.get(TrainingRunRecord, run_id)
                    managed_directories = managed_uploaded_weight_directories(
                        session,
                        [record] if record is not None else [],
                    )
                uploaded_weight_directory = managed_directories[0] if managed_directories else None
            if cascade:
                if run.status in {"queued", "running", "evaluating", "exporting", "verifying"}:
                    raise HTTPException(status_code=409, detail="active training runs cannot be cascade deleted")
                run_artifacts = [Path(run.run_directory).resolve()] if delete_artifacts and run.run_directory else []
                if uploaded_weight_directory is not None:
                    run_artifacts.append(uploaded_weight_directory)
                validate_artifact_paths(run_artifacts)
                with session_scope(registry) as session:
                    model_ids = list(session.scalars(select(ModelVersionRecord.id).where(ModelVersionRecord.training_run_id == run_id)))
                    artifact_paths = delete_downstream_records(session, model_ids, delete_artifacts=delete_artifacts)
                    record = session.get(TrainingRunRecord, run_id)
                    if record is not None:
                        artifact_paths.extend(run_artifacts)
                        session.delete(record)
                validate_artifact_paths(artifact_paths)
                remove_artifact_paths(artifact_paths)
                return Response(status_code=204)
            artifact_directories = [Path(run.run_directory).resolve()] if delete_artifacts and run.run_directory else []
            if uploaded_weight_directory is not None:
                artifact_directories.append(uploaded_weight_directory)
            for artifact_directory in artifact_directories:
                try:
                    artifact_directory.relative_to(root.resolve())
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail="training artifacts are outside storage root") from exc
            training_repository.delete(run_id)
            for artifact_directory in artifact_directories:
                if artifact_directory.is_dir():
                    shutil.rmtree(artifact_directory)
            return Response(status_code=204)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="training run not found") from exc
        except (ActiveTrainingRunDeletion, ReferencedTrainingRunDeletion) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/model-versions", response_model=ModelVersionResponse, status_code=201)
    def create_model_version(req: ModelVersionCreateRequest) -> ModelVersionResponse:
        try:
            run = training_repository.get_required(req.training_run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="training run not found") from exc
        if run.status != "completed":
            raise HTTPException(status_code=409, detail="training run is not completed")
        best_pt = run.artifacts.get("best_pt")
        if not best_pt or not Path(best_pt).is_file():
            raise HTTPException(status_code=409, detail="training run best.pt is missing")
        quality_report = None
        if run.run_directory:
            quality_path = Path(run.run_directory) / "quality-report.json"
            test_metrics_path = Path(run.run_directory) / "test-metrics.json"
            if quality_path.is_file() and test_metrics_path.is_file():
                try:
                    quality_report = json.loads(quality_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    quality_report = None
        try:
            model = model_repository.create(
                ModelVersionSpec(
                    name=req.name,
                    version=req.version,
                    task_type=run.spec.task_type,
                    training_run_id=run.id,
                    dataset_release_id=run.spec.dataset_release_id,
                    selected_classes=run.spec.selected_classes,
                    class_aliases=run.spec.class_aliases,
                    pt_path=best_pt,
                    metrics=run.metrics,
                    quality_report=quality_report,
                ),
                model_id=f"model-{uuid.uuid4().hex}",
            )
        except DuplicateModelRegistration as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _model_response(model)

    @app.get("/api/model-versions", response_model=list[ModelVersionResponse])
    def model_versions() -> list[ModelVersionResponse]:
        return [_model_response(model) for model in model_repository.list()]

    @app.get("/api/model-versions/{model_id}", response_model=ModelVersionResponse)
    def model_version(model_id: str) -> ModelVersionResponse:
        try:
            return _model_response(model_repository.get_required(model_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="model version not found") from exc

    @app.get("/api/model-versions/{model_id}/gate-report", response_model=ModelGateReportResponse)
    def model_gate_report(model_id: str) -> ModelGateReportResponse:
        try:
            model = model_repository.get_required(model_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="model version not found") from exc
        if not model.gate_report_path:
            return ModelGateReportResponse(available=False, reason="not_generated")

        report_path = Path(model.gate_report_path)
        if not report_path.is_absolute():
            report_path = root / report_path
        report_path = report_path.resolve()
        try:
            report_path.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="model gate report is outside storage root") from exc
        if not report_path.is_file():
            return ModelGateReportResponse(available=False, reason="missing")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=409, detail="model gate report is invalid") from exc
        if not isinstance(report, dict):
            raise HTTPException(status_code=409, detail="model gate report is invalid")
        return ModelGateReportResponse(available=True, report=report)

    @app.get("/api/model-versions/{model_id}/gate-runs", response_model=list[ModelGateRunResponse])
    def model_gate_runs(model_id: str) -> list[ModelGateRunResponse]:
        try:
            model = model_repository.get_required(model_id)
            runs = list_gate_runs(
                root,
                model_id,
                Path(model.gate_report_path) if model.gate_report_path else None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="model version not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return [ModelGateRunResponse.model_validate(run) for run in runs]

    @app.delete(
        "/api/model-versions/{model_id}/gate-runs/{run_id}",
        response_model=ModelGateRunDeleteResponse,
    )
    def delete_model_gate_run(model_id: str, run_id: str) -> ModelGateRunDeleteResponse:
        try:
            model = model_repository.get_required(model_id)
            directory = gate_run_directory(root, model_id, run_id)
            runs = list_gate_runs(
                root,
                model_id,
                Path(model.gate_report_path) if model.gate_report_path else None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="model version not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        target = next((run for run in runs if run["id"] == run_id), None)
        if target is None or directory.is_symlink() or not directory.is_dir():
            raise HTTPException(status_code=404, detail="model gate run not found")
        if target["active"] and model.status == "published":
            raise HTTPException(
                status_code=409,
                detail="published model is using this gate run; archive it or run a newer gate before deletion",
            )

        fallback_run_id = None
        updated = model
        if target["active"]:
            fallback = next(
                (
                    run for run in runs
                    if run["id"] != run_id and run["status"] != "incomplete" and run["onnx"] is not None
                ),
                None,
            )
            if fallback is None:
                updated = model_repository.clear_gate_run(model_id)
            else:
                result = read_gate_run_result(root, model_id, fallback["id"])
                if result is None:
                    raise HTTPException(status_code=409, detail="fallback gate report is unavailable")
                artifacts = dict(result.get("artifacts") or {})
                artifacts["onnx"] = dict(fallback["onnx"])
                updated = model_repository.activate_gate_run(
                    model_id,
                    gates=dict(result.get("gates") or {}),
                    artifacts=artifacts,
                    environment=dict(result.get("environment") or {}),
                    gate_report_path=str(gate_run_directory(root, model_id, fallback["id"]) / "result.json"),
                )
                fallback_run_id = fallback["id"]

        deleted_size = int(target["total_size_bytes"])
        try:
            shutil.rmtree(directory)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail=f"gate references were updated but files could not be removed: {exc}",
            ) from exc
        return ModelGateRunDeleteResponse(
            deleted_run_id=run_id,
            deleted_size_bytes=deleted_size,
            fallback_run_id=fallback_run_id,
            model=_model_response(updated),
        )

    @app.post("/api/model-versions/{model_id}/gates", response_model=ModelVersionResponse)
    @heavy_operation("model-gates")
    def run_model_gates(model_id: str) -> ModelVersionResponse:
        if any(run.status in {"running", "evaluating", "exporting", "verifying"} for run in training_repository.list()):
            raise HTTPException(status_code=409, detail="another GPU operation is active")
        if any(run["status"] in {"queued", "running"} for run in inference_repository.list()):
            raise HTTPException(status_code=409, detail="another GPU operation is active")
        try:
            model = model_repository.get_required(model_id)
            run = training_repository.get_required(model.spec.training_run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="model version not found") from exc
        if not Path(model.spec.pt_path).is_file():
            raise HTTPException(status_code=409, detail="model PT artifact is missing")
        with session_scope(registry) as session:
            release = session.get(DatasetRelease, model.spec.dataset_release_id)
            if release is None:
                raise HTTPException(status_code=409, detail="dataset release is missing")
            data_yaml = (root / release.release_path / "data.yaml").resolve()
            if not data_yaml.is_file():
                raise HTTPException(status_code=409, detail="dataset release data.yaml is missing")
        try:
            result, report_path = gate_executor.run(model_id, {
                "model_id": model_id,
                "task_type": model.spec.task_type,
                "pt_path": model.spec.pt_path,
                "data_yaml_path": str(data_yaml),
                "image_size": run.spec.image_size,
                "device": run.spec.device,
            })
        except ModelGateError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        updated = model_repository.update_gates(
            model_id,
            result["gates"],
            artifacts=result.get("artifacts", {}),
            environment=result.get("environment", {}),
            gate_report_path=str(report_path),
        )
        return _model_response(updated)

    @app.post("/api/model-versions/{model_id}/publish", response_model=ModelVersionResponse)
    def publish_model(model_id: str) -> ModelVersionResponse:
        try:
            return _model_response(model_repository.publish(model_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="model version not found") from exc
        except InvalidModelTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/model-versions/{model_id}/archive", response_model=ModelVersionResponse)
    def archive_model(model_id: str) -> ModelVersionResponse:
        try:
            return _model_response(model_repository.archive(model_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="model version not found") from exc
        except InvalidModelTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/model-versions/{model_id}/export")
    def export_model_version(model_id: str) -> Response:
        try:
            model = model_repository.get_required(model_id)
            payload, filename = build_release_bundle(root, model)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="model version not found") from exc
        except ReleaseBundleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(
            content=payload,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.delete("/api/model-versions/{model_id}", status_code=204)
    def delete_model(model_id: str, delete_artifacts: bool = False, cascade: bool = False) -> Response:
        try:
            model = model_repository.get_required(model_id)
            if cascade:
                with session_scope(registry) as session:
                    artifact_paths = delete_downstream_records(session, [model_id], delete_artifacts=delete_artifacts)
                validate_artifact_paths(artifact_paths)
                remove_artifact_paths(artifact_paths)
                return Response(status_code=204)
            artifact_paths: list[Path] = []
            if delete_artifacts:
                # Training weights are shared by all model versions for a run.
                # Only model-owned gate artifacts may be removed here.
                candidates = [
                    artifact.get("path", "")
                    for name, artifact in model.artifacts.items()
                    if name != "pt"
                ]
                for value in candidates:
                    if not value:
                        continue
                    candidate = Path(value).resolve()
                    try:
                        candidate.relative_to(root.resolve())
                    except ValueError as exc:
                        raise HTTPException(status_code=409, detail="model artifacts are outside storage root") from exc
                    artifact_paths.append(candidate)
            model_repository.delete(model_id)
            for artifact_path in set(artifact_paths):
                if artifact_path.is_file():
                    artifact_path.unlink()
            return Response(status_code=204)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="model version not found") from exc
        except (PublishedModelDeletion, ReferencedModelDeletion) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/imported-models", response_model=ImportedModelResponse, status_code=201)
    async def import_test_model(
        name: str = Form(...),
        task_type: str = Form(...),
        class_names: str = Form("[]"),
        file: UploadFile = File(...),
    ) -> ImportedModelResponse:
        normalized_name = name.strip()
        if not normalized_name:
            raise HTTPException(status_code=422, detail="model name must not be blank")
        if task_type not in {"detect", "segment"}:
            raise HTTPException(status_code=422, detail="task type must be detect or segment")
        filename = safe_upload_name(file, {".pt", ".onnx"}, "model file")
        artifact_format = Path(filename).suffix.lower().lstrip(".")
        try:
            provided_classes = json.loads(class_names)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="class_names must be a JSON array") from exc
        if not isinstance(provided_classes, list) or any(not isinstance(item, str) or not item.strip() for item in provided_classes):
            raise HTTPException(status_code=422, detail="class_names must be a JSON array of non-empty strings")

        model_id = f"imported-model-{uuid.uuid4().hex}"
        model_directory = root / "imported-models" / model_id
        destination = model_directory / filename
        try:
            if await save_uploaded_file(file, destination) == 0:
                raise HTTPException(status_code=422, detail="model file is empty")
            try:
                inspected = imported_model_inspector(destination, artifact_format, task_type)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"model file could not be loaded: {exc}") from exc
            discovered_task = str(inspected.get("task_type") or "")
            if discovered_task and discovered_task != task_type:
                raise HTTPException(status_code=422, detail=f"model task is {discovered_task}, not {task_type}")
            discovered_classes = inspected.get("class_names") or []
            effective_classes = tuple(str(item) for item in (provided_classes or discovered_classes))
            metadata = file_metadata(destination)
            model = imported_model_repository.create(
                model_id=model_id, name=normalized_name, task_type=task_type,
                artifact_format=artifact_format, original_name=filename,
                artifact_path=metadata["path"], size_bytes=metadata["size_bytes"],
                sha256=metadata["sha256"], class_names=effective_classes,
            )
            return _imported_model_response(model)
        except Exception:
            if imported_model_repository.get(model_id) is None:
                shutil.rmtree(model_directory, ignore_errors=True)
            raise

    @app.get("/api/imported-models", response_model=list[ImportedModelResponse])
    def imported_models() -> list[ImportedModelResponse]:
        return [_imported_model_response(model) for model in imported_model_repository.list()]

    @app.delete("/api/imported-models/{model_id}", status_code=204)
    def delete_imported_model(model_id: str, delete_artifact: bool = True) -> Response:
        try:
            model = imported_model_repository.get_required(model_id)
            artifact_path = require_path_within(
                Path(model.artifact_path), root / "imported-models",
                "imported model artifact is outside managed storage",
            )
            imported_model_repository.delete(model_id)
            if delete_artifact and artifact_path.is_file():
                artifact_path.unlink()
                try:
                    artifact_path.parent.rmdir()
                except OSError:
                    pass
            return Response(status_code=204)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="imported model not found") from exc
        except ReferencedImportedModelDeletion as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/inference-runs", response_model=InferenceRunResponse, status_code=201)
    @heavy_operation("inference")
    def create_inference_run(req: InferenceRunCreateRequest) -> InferenceRunResponse:
        if req.mode not in {"image", "batch", "video"}:
            raise HTTPException(status_code=422, detail="mode must be image, batch or video")
        if req.runtime not in {"pt", "onnx"}:
            raise HTTPException(status_code=422, detail="runtime must be pt or onnx")
        model = None
        imported_model = None
        if req.model_version_id:
            try:
                model = model_repository.get_required(req.model_version_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="model version not found") from exc
            if model.status == "archived":
                raise HTTPException(status_code=409, detail="archived models cannot start new inference runs")
        else:
            try:
                imported_model = imported_model_repository.get_required(req.imported_model_id or "")
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="imported model not found") from exc
        imports_root = root / "imports"
        sources = [
            require_path_within(Path(source), imports_root, "inference sources must be inside the managed imports directory")
            for source in req.sources
        ]
        if any(not source.is_file() for source in sources):
            raise HTTPException(status_code=409, detail="one or more inference sources do not exist")
        if req.mode in {"image", "video"} and len(sources) != 1:
            raise HTTPException(status_code=409, detail=f"{req.mode} mode requires exactly one source")
        if any(run.status in {"running", "evaluating", "exporting", "verifying"} for run in training_repository.list()):
            raise HTTPException(status_code=409, detail="another GPU operation is active")
        if any(run["status"] in {"queued", "running"} for run in inference_repository.list()):
            raise HTTPException(status_code=409, detail="another GPU operation is active")

        artifact_path = None
        if model is not None:
            artifact = model.artifacts.get(req.runtime, {})
            artifact_path = artifact.get("path") if isinstance(artifact, dict) else None
            if req.runtime == "pt" and not artifact_path:
                artifact_path = model.spec.pt_path
            task_type = model.spec.task_type
        else:
            if req.runtime != imported_model.artifact_format:
                raise HTTPException(status_code=409, detail=f"imported model only provides {imported_model.artifact_format.upper()}")
            artifact_path = imported_model.artifact_path
            task_type = imported_model.task_type
        if not artifact_path or not Path(artifact_path).is_file():
            raise HTTPException(status_code=409, detail=f"model {req.runtime.upper()} artifact is missing")

        run_id = f"inference-{uuid.uuid4().hex}"
        inference_repository.create(
            run_id=run_id,
            model_version_id=model.id if model is not None else None,
            imported_model_id=imported_model.id if imported_model is not None else None,
            mode=req.mode,
            runtime=req.runtime,
            sources=[str(source) for source in sources],
            confidence=req.confidence,
        )
        payload = {
            "model_version_id": model.id if model is not None else None,
            "imported_model_id": imported_model.id if imported_model is not None else None,
            "task_type": task_type,
            "artifact_path": str(Path(artifact_path).resolve()),
            "runtime": req.runtime,
            "mode": req.mode,
            "sources": [str(source) for source in sources],
            "confidence": req.confidence,
            "device": "cpu" if req.runtime == "onnx" else "cuda:0",
        }
        if hasattr(local_inference_executor, "start"):
            try:
                return _inference_response(local_inference_executor.start(run_id, payload))
            except InferenceExecutionError as exc:
                failed = inference_repository.update(run_id, "failed", progress=100, message=str(exc))
                return _inference_response(failed)
        inference_repository.update(run_id, "running", progress=5, message="Inference runner started")
        try:
            result, output_directory, result_path = local_inference_executor.run(run_id, payload)
        except InferenceExecutionError as exc:
            failed = inference_repository.update(run_id, "failed", progress=100, message=str(exc))
            return _inference_response(failed)
        completed = inference_repository.update(
            run_id,
            "completed",
            progress=100,
            message=f"Completed {len(result.get('items', []))} item(s)",
            output_directory=str(output_directory),
            result_path=str(result_path),
        )
        return _inference_response(completed)

    @app.post("/api/inference-runs/upload", response_model=InferenceRunResponse, status_code=201)
    async def create_inference_run_from_upload(
        model_version_id: str | None = Form(None),
        imported_model_id: str | None = Form(None),
        mode: str = Form(...),
        runtime: str = Form(...),
        confidence: float = Form(...),
        files: list[UploadFile] = File(...),
    ) -> InferenceRunResponse:
        if mode not in {"image", "batch", "video"}:
            raise HTTPException(status_code=422, detail="mode must be image, batch or video")
        if not files:
            raise HTTPException(status_code=422, detail="at least one inference file is required")
        if mode in {"image", "video"} and len(files) != 1:
            raise HTTPException(status_code=422, detail=f"{mode} mode requires exactly one file")
        allowed_extensions = VIDEO_EXTENSIONS if mode == "video" else {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
        filenames: list[str] = []
        for upload in files:
            filename = safe_upload_name(upload, allowed_extensions, "inference file")
            if filename.casefold() in {item.casefold() for item in filenames}:
                raise HTTPException(status_code=422, detail=f"duplicate inference filename: {filename}")
            filenames.append(filename)

        staging_dir = root / "imports" / "inference-uploads" / uuid.uuid4().hex
        try:
            sources: list[str] = []
            for upload, filename in zip(files, filenames):
                destination = staging_dir / filename
                if await save_uploaded_file(upload, destination) == 0:
                    raise HTTPException(status_code=422, detail=f"inference file is empty: {filename}")
                sources.append(str(destination.resolve()))
            request = InferenceRunCreateRequest(
                model_version_id=model_version_id,
                imported_model_id=imported_model_id,
                mode=mode,
                runtime=runtime,
                sources=sources,
                confidence=confidence,
            )
            return create_inference_run(request)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

    @app.get("/api/inference-runs", response_model=list[InferenceRunResponse])
    def inference_runs() -> list[InferenceRunResponse]:
        return [_inference_response(run) for run in inference_repository.list()]

    @app.get("/api/inference-runs/{run_id}", response_model=InferenceRunResponse)
    def inference_run(run_id: str) -> InferenceRunResponse:
        try:
            return _inference_response(inference_repository.get_required(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="inference run not found") from exc

    @app.post("/api/inference-runs/{run_id}/refresh", response_model=InferenceRunResponse)
    def refresh_inference_run(run_id: str) -> InferenceRunResponse:
        try:
            if hasattr(local_inference_executor, "refresh"):
                return _inference_response(local_inference_executor.refresh(run_id))
            return _inference_response(inference_repository.get_required(run_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="inference run not found") from exc

    @app.post("/api/inference-runs/{run_id}/cancel", response_model=InferenceRunResponse)
    def cancel_inference_run(run_id: str) -> InferenceRunResponse:
        try:
            if hasattr(local_inference_executor, "cancel"):
                return _inference_response(local_inference_executor.cancel(run_id))
            return _inference_response(inference_repository.update(run_id, "cancelled", progress=0, message="Cancellation requested"))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="inference run not found") from exc

    @app.delete("/api/inference-runs/{run_id}", status_code=204)
    def delete_inference_run(run_id: str, delete_artifacts: bool = False) -> Response:
        try:
            run = inference_repository.get_required(run_id)
            output_directory = Path(run["output_directory"]).resolve() if delete_artifacts and run["output_directory"] else None
            source_directories = {
                Path(source).resolve().parent
                for source in run["sources"]
                if delete_artifacts and Path(source).resolve().is_relative_to((root / "imports" / "inference-uploads").resolve())
            }
            if output_directory is not None:
                try:
                    output_directory.relative_to(root.resolve())
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail="inference outputs are outside storage root") from exc
            inference_repository.delete(run_id)
            if output_directory is not None and output_directory.is_dir():
                shutil.rmtree(output_directory)
            for source_directory in source_directories:
                if source_directory.is_dir():
                    shutil.rmtree(source_directory)
            return Response(status_code=204)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="inference run not found") from exc
        except ActiveInferenceRunDeletion as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/artifacts")
    def artifact(path: str) -> FileResponse:
        requested = Path(path).expanduser()
        candidate = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="artifact is outside the storage root") from exc
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(candidate)

    @app.post("/api/annotation-images/sync", response_model=AnnotationSyncResponse)
    def sync_annotation_images(req: AnnotationSyncRequest) -> AnnotationSyncResponse:
        try:
            synced_count, total_count = annotation_repository.sync_selected_frame_counts(req.task_id)
            return AnnotationSyncResponse(synced_count=synced_count, total_count=total_count)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        except AnnotationSourceUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/annotation-images", response_model=AnnotationImagePageResponse)
    def annotation_images(
        task_id: str | None = None,
        status: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(30, ge=1, le=100),
    ) -> AnnotationImagePageResponse:
        items, total, status_counts = annotation_repository.list_page(
            task_id=task_id,
            status=status,
            page=page,
            page_size=page_size,
        )
        return AnnotationImagePageResponse(
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            status_counts=status_counts,
        )

    @app.get("/api/annotation-images/{frame_id}", response_model=AnnotationImageResponse)
    def annotation_image(frame_id: str) -> AnnotationImageResponse:
        try:
            return _annotation_response(annotation_repository.get_required(frame_id))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="annotation image not found") from exc

    @app.get("/api/annotation-images/{frame_id}/content")
    def annotation_image_content(frame_id: str) -> FileResponse:
        try:
            path = Path(annotation_repository.get_required(frame_id).image_path).resolve()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="annotation image not found") from exc
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="annotation image is outside storage root") from exc
        return FileResponse(path)

    @app.get("/api/annotation-images/{frame_id}/thumbnail")
    def annotation_image_thumbnail(frame_id: str) -> FileResponse:
        try:
            source_path = Path(annotation_repository.get_required(frame_id).image_path).resolve()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="annotation image not found") from exc
        try:
            source_path.relative_to(root)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="annotation image is outside storage root") from exc
        if not source_path.is_file():
            raise HTTPException(status_code=404, detail="annotation image file not found")

        cache_dir = root / "thumbnails" / "annotations"
        cache_path = cache_dir / f"{hashlib.sha256(frame_id.encode('utf-8')).hexdigest()}.jpg"
        if not cache_path.is_file():
            cache_dir.mkdir(parents=True, exist_ok=True)
            temporary_path = cache_path.with_suffix(f".{uuid.uuid4().hex}.tmp")
            try:
                with Image.open(source_path) as source:
                    thumbnail = ImageOps.exif_transpose(source)
                    thumbnail.thumbnail((160, 120))
                    if thumbnail.mode != "RGB":
                        thumbnail = thumbnail.convert("RGB")
                    thumbnail.save(temporary_path, format="JPEG", quality=82, optimize=True)
                temporary_path.replace(cache_path)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()
        return FileResponse(cache_path, media_type="image/jpeg")

    @app.post("/api/annotation-images/{frame_id}/shapes", response_model=AnnotationImageResponse, status_code=201)
    def create_annotation_shape(frame_id: str, req: AnnotationShapeMutationRequest) -> AnnotationImageResponse:
        try:
            _, image = annotation_repository.create_shape(frame_id, revision=req.revision, class_id=req.class_id, class_name=req.class_name, shape_type=req.shape_type, coordinates=req.coordinates, source=req.source)
            return _annotation_response(image)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="annotation image not found") from exc
        except AnnotationConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidAnnotationTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (GeometryError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.put("/api/annotation-images/{frame_id}/shapes/{shape_id}", response_model=AnnotationImageResponse)
    def update_annotation_shape(frame_id: str, shape_id: str, req: AnnotationShapeMutationRequest) -> AnnotationImageResponse:
        try:
            return _annotation_response(annotation_repository.update_shape(frame_id, shape_id, revision=req.revision, class_id=req.class_id, class_name=req.class_name, coordinates=req.coordinates))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="annotation shape not found") from exc
        except AnnotationConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidAnnotationTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (GeometryError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.delete("/api/annotation-images/{frame_id}/shapes/{shape_id}", response_model=AnnotationImageResponse)
    def delete_annotation_shape(frame_id: str, shape_id: str, revision: int) -> AnnotationImageResponse:
        try:
            return _annotation_response(annotation_repository.delete_shape(frame_id, shape_id, revision=revision))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="annotation shape not found") from exc
        except (AnnotationConflict, InvalidAnnotationTransition) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/annotation-images/{frame_id}/status", response_model=AnnotationImageResponse)
    def set_annotation_status(frame_id: str, req: AnnotationStatusRequest) -> AnnotationImageResponse:
        try:
            return _annotation_response(annotation_repository.set_status(frame_id, revision=req.revision, status=req.status))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="annotation image not found") from exc
        except (AnnotationConflict, InvalidAnnotationTransition) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/annotation-exports/native", status_code=201)
    def native_annotation_export(req: NativeAnnotationExportRequest) -> dict:
        try:
            result = export_reviewed_annotations(req.task_id, req.export_name, root, registry)
            return {"export_id": result.export_id, "extracted_root": str(result.extracted_root), "sample_count": result.sample_count}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/annotation-images/{frame_id}/sam", response_model=AnnotationImageResponse, status_code=201)
    @heavy_operation("sam")
    def suggest_annotation_with_sam(frame_id: str, req: SamSuggestionRequest) -> AnnotationImageResponse:
        if any(run["status"] in {"queued", "running"} for run in inference_repository.list()):
            raise HTTPException(status_code=409, detail="another GPU operation is active")
        if req.model not in {"sam2_t.pt", "sam2_s.pt"}:
            raise HTTPException(status_code=422, detail="SAM model must be sam2_t.pt or sam2_s.pt")
        if len(req.point) != 2 or any(value < 0 or value > 1 for value in req.point):
            raise HTTPException(status_code=422, detail="SAM point must be normalized to [0, 1]")
        try:
            image = annotation_repository.get_required(frame_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="annotation image not found") from exc
        if image.task_type != "segment":
            raise HTTPException(status_code=409, detail="SAM suggestions require a segment task")
        try:
            result, _ = local_sam_executor.run(frame_id, {"model": req.model, "image_path": image.image_path, "point": req.point})
            _, updated = annotation_repository.create_shape(frame_id, revision=req.revision, class_id=req.class_id, class_name=req.class_name, shape_type="polygon", coordinates=result["polygon"], source="sam2")
            return _annotation_response(updated)
        except SamExecutionError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except AnnotationConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except InvalidAnnotationTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (GeometryError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/api/annotation-images/{frame_id}/sam/preview")
    @heavy_operation("sam-preview")
    def preview_annotation_with_sam(frame_id: str, req: SamPreviewRequest) -> dict:
        if req.model not in {"sam2_t.pt", "sam2_s.pt"}:
            raise HTTPException(status_code=422, detail="SAM model must be sam2_t.pt or sam2_s.pt")
        try:
            image = annotation_repository.get_required(frame_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="annotation image not found") from exc
        if image.task_type != "segment":
            raise HTTPException(status_code=409, detail="SAM previews require a segment task")
        try:
            result, _ = local_sam_executor.run(frame_id, {"model": req.model, "image_path": image.image_path, "positive_points": req.positive_points, "negative_points": req.negative_points, "simplify": req.simplify})
            return {"polygon": result["polygon"], "model": result["model"], "model_was_loaded": result.get("model_was_loaded", False)}
        except SamExecutionError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except (GeometryError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/frame-batches")
    def list_all_batches() -> list[dict]:
        with session_scope(registry) as session:
            batches = list(session.scalars(select(FrameBatch).order_by(FrameBatch.created_at.desc())))
        return [{"id": b.id, "collection_id": b.collection_id} for b in batches]

    @app.delete("/api/frame-batches/{batch_id}", status_code=204)
    def delete_frame_batch(batch_id: str, delete_artifacts: bool = False) -> Response:
        with session_scope(registry) as session:
            batch = session.get(FrameBatch, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="frame batch not found")
            artifact_directory = (root / batch.manifest_path).resolve().parent if delete_artifacts else None
            if artifact_directory is not None:
                try:
                    artifact_directory.relative_to(root.resolve())
                except ValueError as exc:
                    raise HTTPException(status_code=409, detail="frame batch artifacts are outside storage root") from exc
            frame_ids = list(session.scalars(select(FrameAsset.id).where(FrameAsset.batch_id == batch_id)))
            if frame_ids:
                session.execute(delete(AnnotationShapeRecord).where(AnnotationShapeRecord.frame_id.in_(frame_ids)))
                session.execute(delete(AnnotationImageRecord).where(AnnotationImageRecord.frame_id.in_(frame_ids)))
                session.execute(delete(FrameAsset).where(FrameAsset.id.in_(frame_ids)))
            session.delete(batch)
        if artifact_directory is not None and artifact_directory.is_dir():
            shutil.rmtree(artifact_directory)
        return Response(status_code=204)

    @app.delete("/api/video-collections/{collection_id}", status_code=204)
    def delete_video_collection(collection_id: str, delete_artifacts: bool = False, cascade: bool = False) -> Response:
        artifact_paths: list[Path] = []
        with session_scope(registry) as session:
            collection = session.get(VideoCollection, collection_id)
            if collection is None:
                raise HTTPException(status_code=404, detail="video collection not found")
            batches = list(session.scalars(select(FrameBatch).where(FrameBatch.collection_id == collection_id)))
            if batches and not cascade:
                batch_id = batches[0].id
                raise HTTPException(status_code=409, detail=f"video collection has frame batch {batch_id}; delete batches first")
            if cascade:
                batch_ids = [batch.id for batch in batches]
                frame_ids = list(session.scalars(select(FrameAsset.id).where(FrameAsset.batch_id.in_(batch_ids)))) if batch_ids else []
                if frame_ids:
                    session.execute(delete(AnnotationShapeRecord).where(AnnotationShapeRecord.frame_id.in_(frame_ids)))
                    session.execute(delete(AnnotationImageRecord).where(AnnotationImageRecord.frame_id.in_(frame_ids)))
                    session.execute(delete(FrameAsset).where(FrameAsset.id.in_(frame_ids)))
                if delete_artifacts:
                    artifact_paths.extend((root / batch.manifest_path).resolve().parent for batch in batches)
                if batch_ids:
                    session.execute(delete(FrameBatch).where(FrameBatch.id.in_(batch_ids)))
            assets = list(session.scalars(select(VideoAsset).where(VideoAsset.collection_id == collection_id)))
            if delete_artifacts:
                for asset in assets:
                    path = (root / asset.stored_path).resolve()
                    try:
                        path.relative_to(root.resolve())
                    except ValueError as exc:
                        raise HTTPException(status_code=409, detail="video artifacts are outside storage root") from exc
                    artifact_paths.append(path)
            for asset in assets:
                session.delete(asset)
            session.delete(collection)
        validate_artifact_paths(artifact_paths)
        remove_artifact_paths(artifact_paths)
        return Response(status_code=204)

    @app.delete("/api/dataset-releases/{release_id}", status_code=204)
    def delete_dataset_release(release_id: str, delete_artifacts: bool = False, cascade: bool = False) -> Response:
        with session_scope(registry) as session:
            release = session.get(DatasetRelease, release_id)
            if release is None:
                raise HTTPException(status_code=404, detail="dataset release not found")
            if cascade:
                training_records = list(session.scalars(select(TrainingRunRecord).where(TrainingRunRecord.dataset_release_id == release_id)))
                active_training = next((record.id for record in training_records if record.status in {"queued", "running", "evaluating", "exporting", "verifying"}), None)
                if active_training is not None:
                    raise HTTPException(status_code=409, detail=f"active training run {active_training} prevents cascade deletion")
                training_ids = [record.id for record in training_records]
                model_ids = list(session.scalars(select(ModelVersionRecord.id).where(ModelVersionRecord.dataset_release_id == release_id)))
                cascade_artifacts = []
                if delete_artifacts:
                    cascade_artifacts.extend(Path(record.run_directory).resolve() for record in training_records if record.run_directory)
                    cascade_artifacts.extend(managed_uploaded_weight_directories(session, training_records))
                    cascade_artifacts.append((root / release.release_path).resolve())
                    validate_artifact_paths(cascade_artifacts)
                artifact_paths = delete_downstream_records(session, model_ids, delete_artifacts=delete_artifacts)
                artifact_paths.extend(cascade_artifacts)
                if training_ids:
                    session.execute(delete(TrainingRunRecord).where(TrainingRunRecord.id.in_(training_ids)))
                session.delete(release)
                artifact_directory = None
            else:
                artifact_paths = []
                training_id = session.execute(select(TrainingRunRecord.id).where(TrainingRunRecord.dataset_release_id == release_id).limit(1)).scalar_one_or_none()
                if training_id is not None:
                    raise HTTPException(status_code=409, detail=f"dataset release is referenced by training run {training_id}")
                model_id = session.execute(select(ModelVersionRecord.id).where(ModelVersionRecord.dataset_release_id == release_id).limit(1)).scalar_one_or_none()
                if model_id is not None:
                    raise HTTPException(status_code=409, detail=f"dataset release is referenced by model {model_id}")
                artifact_directory = (root / release.release_path).resolve() if delete_artifacts else None
                if artifact_directory is not None:
                    try:
                        artifact_directory.relative_to(root.resolve())
                    except ValueError as exc:
                        raise HTTPException(status_code=409, detail="dataset artifacts are outside storage root") from exc
                session.delete(release)
        if cascade:
            validate_artifact_paths(artifact_paths)
            remove_artifact_paths(artifact_paths)
        if artifact_directory is not None and artifact_directory.is_dir():
            shutil.rmtree(artifact_directory)
        return Response(status_code=204)

    @app.post("/api/image-imports", status_code=201)
    async def import_images(task_id: str = Form(...), batch_id: str = Form(...), files: list[UploadFile] = File(...)) -> dict:
        with session_scope(registry) as session:
            if session.get(Task, task_id) is None:
                raise HTTPException(status_code=404, detail="task not found")
            if session.get(FrameBatch, batch_id) is not None:
                raise HTTPException(status_code=409, detail="frame batch already exists")
        if not files:
            raise HTTPException(status_code=422, detail="at least one image is required")

        collection_id = f"image-import-{batch_id}"
        batch_directory = root / "frame-batches" / task_id / batch_id
        selected_directory = batch_directory / "selected"
        selected_directory.mkdir(parents=True, exist_ok=False)
        imported: list[dict] = []
        assets: list[VideoAsset] = []
        frames: list[FrameAsset] = []
        try:
            for index, upload in enumerate(files):
                original_name = Path(upload.filename or f"image-{index}.jpg").name
                extension = Path(original_name).suffix.lower()
                if extension not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                    raise HTTPException(status_code=422, detail=f"unsupported image format: {original_name}")
                content = await upload.read()
                if not content:
                    raise HTTPException(status_code=422, detail=f"empty image: {original_name}")
                if len(content) > 50 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail=f"image exceeds 50 MB: {original_name}")
                stored_name = f"{index:05d}-{uuid.uuid4().hex[:8]}-{original_name}"
                stored_path = selected_directory / stored_name
                stored_path.write_bytes(content)
                relative_path = stored_path.relative_to(root).as_posix()
                sha256 = hashlib.sha256(content).hexdigest()
                video_id = f"image-source-{uuid.uuid4().hex}"
                frame_id = f"frame-{uuid.uuid4().hex}"
                assets.append(VideoAsset(id=video_id, collection_id=collection_id, original_name=original_name, stored_path=relative_path, sha256=sha256, size_bytes=len(content)))
                frames.append(FrameAsset(id=frame_id, batch_id=batch_id, video_id=video_id, stored_path=relative_path, sha256=sha256, timestamp_ms=0, frame_index=index, status="selected", storage_key=relative_path, size_bytes=len(content)))
                imported.append({"id": frame_id, "filename": stored_name, "stored_path": relative_path, "status": "selected", "frame_index": index})

            manifest_path = batch_directory / "manifest.json"
            manifest_path.write_text(json.dumps({"task_id": task_id, "batch_id": batch_id, "source": "image-upload", "frames": imported}, ensure_ascii=False, indent=2), encoding="utf-8")
            with session_scope(registry) as session:
                session.add(VideoCollection(id=collection_id, task_id=task_id))
            with session_scope(registry) as session:
                session.add(FrameBatch(id=batch_id, collection_id=collection_id, manifest_path=manifest_path.relative_to(root).as_posix()))
                session.add_all(assets)
            with session_scope(registry) as session:
                session.add_all(frames)
        except Exception:
            shutil.rmtree(batch_directory, ignore_errors=True)
            raise
        return {"collection_id": collection_id, "batch_id": batch_id, "imported_count": len(imported), "frames": imported}

    @app.post("/api/frame-batches/{batch_id}/images", status_code=201)
    async def append_batch_images(batch_id: str, files: list[UploadFile] = File(...)) -> dict:
        with session_scope(registry) as session:
            batch = session.get(FrameBatch, batch_id)
            if batch is None:
                raise HTTPException(status_code=404, detail="batch not found")
            collection = session.get(VideoCollection, batch.collection_id)
            if collection is None:
                raise HTTPException(status_code=409, detail="batch collection not found")
            existing_hashes = set(session.scalars(select(FrameAsset.sha256).where(FrameAsset.batch_id == batch_id)))
            max_index = session.scalar(select(func.max(FrameAsset.frame_index)).where(FrameAsset.batch_id == batch_id))
            task_id = collection.task_id
            collection_id = collection.id
            manifest_key = batch.manifest_path
        imported: list[dict] = []
        skipped: list[dict] = []
        assets: list[VideoAsset] = []
        frames: list[FrameAsset] = []
        pending: list[tuple[str, bytes, str]] = []
        next_index = int(max_index if max_index is not None else -1) + 1
        for upload in files:
            original_name = Path(upload.filename or "image.jpg").name
            extension = Path(original_name).suffix.lower()
            if extension not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                raise HTTPException(status_code=422, detail=f"unsupported image format: {original_name}")
            content = await upload.read()
            if not content:
                raise HTTPException(status_code=422, detail=f"empty image: {original_name}")
            if len(content) > 50 * 1024 * 1024:
                raise HTTPException(status_code=413, detail=f"image exceeds 50 MB: {original_name}")
            sha256 = hashlib.sha256(content).hexdigest()
            if sha256 in existing_hashes:
                skipped.append({"filename": original_name, "reason": "duplicate_content"})
                continue
            pending.append((original_name, content, sha256))
            existing_hashes.add(sha256)

        stored_keys: list[str] = []
        try:
            for original_name, content, sha256 in pending:
                stored_name = f"{next_index:05d}-{uuid.uuid4().hex[:8]}-{original_name}"
                storage_key = f"frame-batches/{task_id}/{batch_id}/selected/{stored_name}"
                object_storage.put_bytes(storage_key, content)
                stored_keys.append(storage_key)
                video_id = f"image-source-{uuid.uuid4().hex}"
                frame_id = f"frame-{uuid.uuid4().hex}"
                assets.append(VideoAsset(id=video_id, collection_id=collection_id, original_name=original_name, stored_path=storage_key, sha256=sha256, size_bytes=len(content)))
                frames.append(FrameAsset(id=frame_id, batch_id=batch_id, video_id=video_id, stored_path=storage_key, sha256=sha256, timestamp_ms=0, frame_index=next_index, status="selected", storage_key=storage_key, size_bytes=len(content)))
                imported.append({"id": frame_id, "filename": stored_name, "stored_path": storage_key, "status": "selected", "frame_index": next_index})
                next_index += 1
            if assets:
                with session_scope(registry) as session:
                    session.add_all(assets)
                    session.flush()
                    session.add_all(frames)
        except Exception:
            for storage_key in stored_keys:
                object_storage.delete(storage_key)
            raise

        with session_scope(registry) as session:
            manifest_frames = list(session.scalars(
                select(FrameAsset)
                .where(FrameAsset.batch_id == batch_id, FrameAsset.lifecycle_status == "active")
                .order_by(FrameAsset.frame_index, FrameAsset.id)
            ))
        manifest_path = (root / manifest_key).resolve()
        if root not in manifest_path.parents:
            raise HTTPException(status_code=500, detail="batch manifest is outside storage root")
        if manifest_path.is_file():
            raw_manifest = manifest_path.read_text(encoding="utf-8")
            manifest = (
                yaml.safe_load(raw_manifest)
                if manifest_path.suffix.lower() in {".yaml", ".yml"}
                else json.loads(raw_manifest)
            ) or {}
            if not isinstance(manifest, dict):
                raise HTTPException(status_code=500, detail="batch manifest must be an object")
        else:
            manifest = {"task_id": task_id, "batch_id": batch_id}

        appended_images = manifest.get("appended_images")
        if not isinstance(appended_images, list):
            appended_images = []
        appended_images.extend({**item, "source": "manual-upload"} for item in imported)
        manifest["appended_images"] = appended_images
        if manifest.get("source") == "image-upload":
            manifest["frames"] = [{
                "id": frame.id,
                "filename": Path(frame.stored_path).name,
                "stored_path": frame.stored_path,
                "status": frame.status,
                "frame_index": frame.frame_index,
            } for frame in manifest_frames]

        serialized_manifest = (
            yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
            if manifest_path.suffix.lower() in {".yaml", ".yml"}
            else json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(serialized_manifest, encoding="utf-8")
        return {"batch_id": batch_id, "imported_count": len(imported), "skipped_count": len(skipped), "frames": imported, "skipped": skipped}

    def _release_root(release_id: str) -> Path:
        with session_scope(registry) as session:
            release = session.get(DatasetRelease, release_id)
            if release is None:
                raise HTTPException(status_code=404, detail="dataset release not found")
            release_root = (root / release.release_path).resolve()
        try:
            release_root.relative_to(root.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="dataset release is outside storage root") from exc
        return release_root

    @app.get("/api/dataset-releases/{release_id}/images")
    def dataset_release_images(release_id: str) -> list[dict]:
        release_root = _release_root(release_id)
        if not release_root.is_dir():
            return []
        return [
            {"path": path.relative_to(release_root).as_posix(), "name": path.name, "size_bytes": path.stat().st_size}
            for path in sorted(release_root.rglob("*"))
            if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        ]

    @app.get("/api/dataset-releases/{release_id}/images/content")
    def dataset_release_image_content(release_id: str, path: str) -> FileResponse:
        release_root = _release_root(release_id)
        candidate = (release_root / path).resolve()
        try:
            candidate.relative_to(release_root)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="invalid dataset image path") from exc
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="dataset image not found")
        return FileResponse(candidate)

    @app.get("/api/video-assets/{video_id}/content")
    def video_content(video_id: str) -> FileResponse:
        path = registered_video_path(registry, root, video_id)
        if path is None:
            raise HTTPException(status_code=404, detail="video asset not found")
        return FileResponse(path)

    # UI-2 API Endpoints

    @app.post("/api/video-collections")
    def import_videos(req: VideoImportRequest) -> dict:
        task_config = resolve_task_config(req.task_id)
        if task_config is None:
            raise HTTPException(status_code=404, detail=f"Task config for {req.task_id} not found")

        source_path = Path(req.source_dir).resolve()
        imports_root = (root / "imports").resolve()
        try:
            source_path.relative_to(imports_root)
        except ValueError as exc:
            raise HTTPException(
                status_code=403,
                detail="source directory must be inside the storage imports directory",
            ) from exc
        if not source_path.is_dir():
            raise HTTPException(status_code=400, detail=f"Source directory does not exist: {req.source_dir}")

        job_id = job_tracker.start_background_task(
            bg_video_import,
            args={
                "task_id": req.task_id,
                "collection_id": req.collection_id,
                "source_dir": str(source_path),
                "storage_root": root,
                "registry": registry,
                "task_config": task_config,
            },
            message=f"正在从目录导入视频到 {req.collection_id}"
        )
        return {"job_id": job_id}

    @app.post("/api/video-collections/upload", status_code=202)
    async def upload_videos(
        task_id: str = Form(...),
        collection_id: str = Form(...),
        files: list[UploadFile] = File(...),
    ) -> dict:
        task_config = resolve_task_config(task_id)
        if task_config is None:
            raise HTTPException(status_code=404, detail=f"Task config for {task_id} not found")
        with session_scope(registry) as session:
            if session.get(VideoCollection, collection_id) is not None:
                raise HTTPException(status_code=409, detail=f"collection already exists: {collection_id}")
        if not files:
            raise HTTPException(status_code=422, detail="at least one video file is required")

        filenames: list[str] = []
        for upload in files:
            raw_name = upload.filename or ""
            filename = Path(raw_name.replace("\\", "/")).name
            if not filename or filename != raw_name.replace("\\", "/"):
                raise HTTPException(status_code=422, detail="video filename must not contain a path")
            if Path(filename).suffix.lower() not in VIDEO_EXTENSIONS:
                raise HTTPException(status_code=422, detail=f"unsupported video extension: {filename}")
            if filename.casefold() in {item.casefold() for item in filenames}:
                raise HTTPException(status_code=422, detail=f"duplicate video filename: {filename}")
            filenames.append(filename)

        staging_dir = root / "imports" / "video-uploads" / uuid.uuid4().hex
        staging_dir.mkdir(parents=True)
        try:
            for upload, filename in zip(files, filenames):
                destination = staging_dir / filename
                bytes_written = await save_uploaded_file(upload, destination)
                if bytes_written == 0:
                    raise HTTPException(status_code=422, detail=f"video file is empty: {filename}")
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

        job_id = job_tracker.start_background_task(
            bg_video_import,
            args={
                "task_id": task_id,
                "collection_id": collection_id,
                "source_dir": str(staging_dir),
                "storage_root": root,
                "registry": registry,
                "task_config": task_config,
                "cleanup_source": True,
            },
            message=f"正在归档 {len(files)} 个上传视频到 {collection_id}",
        )
        return {
            "job_id": job_id,
            "uploaded_count": len(files),
            "filenames": filenames,
        }

    @app.post("/api/frame-batches/{batch_id}/videos", status_code=202)
    async def append_videos_to_existing_batch(
        batch_id: str,
        interval: float = Form(1.0),
        quality: int = Form(95),
        files: list[UploadFile] = File(...),
    ) -> dict:
        if interval <= 0:
            raise HTTPException(status_code=422, detail="frame interval must be positive")
        if not 1 <= quality <= 100:
            raise HTTPException(status_code=422, detail="JPEG quality must be between 1 and 100")
        with session_scope(registry) as session:
            if session.get(FrameBatch, batch_id) is None:
                raise HTTPException(status_code=404, detail="frame batch not found")
        if not files:
            raise HTTPException(status_code=422, detail="at least one video file is required")

        filenames: list[str] = []
        for upload in files:
            filename = safe_upload_name(upload, VIDEO_EXTENSIONS, "video")
            if filename.casefold() in {item.casefold() for item in filenames}:
                raise HTTPException(status_code=422, detail=f"duplicate video filename: {filename}")
            filenames.append(filename)

        staging_dir = root / "imports" / "video-uploads" / uuid.uuid4().hex
        try:
            for upload, filename in zip(files, filenames):
                destination = staging_dir / filename
                if await save_uploaded_file(upload, destination) == 0:
                    raise HTTPException(status_code=422, detail=f"video file is empty: {filename}")
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            raise

        job_id = job_tracker.start_background_task(
            bg_append_batch_videos,
            args={
                "batch_id": batch_id,
                "source_dir": str(staging_dir),
                "storage_root": root,
                "registry": registry,
                "interval": interval,
                "quality": quality,
            },
            message=f"正在向批次 {batch_id} 追加 {len(files)} 个视频并抽帧",
        )
        return {
            "job_id": job_id,
            "uploaded_count": len(files),
            "filenames": filenames,
        }

    @app.get("/api/jobs/{job_id}", response_model=JobStatus)
    def get_job_status(job_id: str) -> JobStatus:
        job = job_tracker.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @app.post("/api/frame-batches")
    def extract_frames(req: FrameExtractRequest) -> dict:
        # Check if collection exists and get its task_id
        with session_scope(registry) as session:
            collection = session.get(VideoCollection, req.collection_id)
            if collection is None:
                raise HTTPException(status_code=404, detail=f"Collection not found: {req.collection_id}")
            task_id = collection.task_id

        job_id = job_tracker.start_background_task(
            bg_frame_extract,
            args={
                "collection_id": req.collection_id,
                "batch_id": req.batch_id,
                "interval": req.interval,
                "quality": req.quality,
                "storage_root": root,
                "registry": registry,
                "task_id": task_id
            },
            message=f"正在为采集批次 {req.collection_id} 抽帧"
        )
        return {"job_id": job_id}

    def _frame_filters(batch_id: str, status: str | None, search: str):
        filters = [FrameAsset.batch_id == batch_id, FrameAsset.lifecycle_status == "active"]
        if status:
            filters.append(FrameAsset.status == status)
        if search.strip():
            filters.append(func.lower(FrameAsset.stored_path).contains(search.strip().lower()))
        return filters

    @app.get("/api/frame-batches/{batch_id}/frames", response_model=FramePageResponse)
    def list_batch_frames(
        batch_id: str,
        page: int = Query(1, ge=1),
        page_size: int = Query(60, ge=1, le=120),
        status: str | None = Query(None, pattern=r"^(candidate|selected|rejected|duplicate)$"),
        search: str = Query("", max_length=200),
    ) -> FramePageResponse:
        with session_scope(registry) as session:
            if session.get(FrameBatch, batch_id) is None:
                raise HTTPException(status_code=404, detail="batch not found")
            filters = _frame_filters(batch_id, status, search)
            total = session.scalar(select(func.count()).select_from(FrameAsset).where(*filters)) or 0
            frames = list(session.scalars(select(FrameAsset).where(*filters).order_by(FrameAsset.frame_index, FrameAsset.id).offset((page - 1) * page_size).limit(page_size)))
            raw_counts = dict(session.execute(select(FrameAsset.status, func.count()).where(FrameAsset.batch_id == batch_id, FrameAsset.lifecycle_status == "active").group_by(FrameAsset.status)).all())
        return FramePageResponse(
            items=[FrameAssetSummary(
                id=f.id,
                filename=Path(f.stored_path).name,
                stored_path=f.stored_path,
                status=f.status,
                rejection_reason=f.rejection_reason,
                timestamp_ms=f.timestamp_ms,
                frame_index=f.frame_index,
                video_id=f.video_id
            ) for f in frames],
            page=page,
            page_size=page_size,
            total=total,
            status_counts=FrameStatusCounts(**{name: raw_counts.get(name, 0) for name in ("candidate", "selected", "rejected", "duplicate")}),
        )

    def _selected_frame_ids(batch_id: str, selection: FrameTrashRequest) -> list[str]:
        with session_scope(registry) as session:
            if session.get(FrameBatch, batch_id) is None:
                raise HTTPException(status_code=404, detail="batch not found")
            if selection.mode == "explicit":
                filters = [FrameAsset.batch_id == batch_id, FrameAsset.lifecycle_status == "active", FrameAsset.id.in_(selection.ids)]
            else:
                filters = _frame_filters(batch_id, selection.status, selection.search)
                if selection.excluded_ids:
                    filters.append(FrameAsset.id.not_in(selection.excluded_ids))
            return list(session.scalars(select(FrameAsset.id).where(*filters).order_by(FrameAsset.id)))

    @app.post("/api/frame-batches/{batch_id}/frames/trash")
    def trash_batch_frames(batch_id: str, req: FrameTrashRequest) -> dict:
        frame_ids = _selected_frame_ids(batch_id, req)
        if not frame_ids:
            raise HTTPException(status_code=409, detail="selection matches no active images")
        affected = recycle_bin.trash(frame_ids, request_id=req.request_id)
        return {"affected_count": affected, "retention_days": 7}

    @app.get("/api/recycle-bin/frames")
    def list_recycled_frames(
        page: int = Query(1, ge=1),
        page_size: int = Query(30, ge=1, le=120),
        batch_id: str | None = None,
        search: str = Query("", max_length=200),
    ) -> dict:
        filters = [FrameAsset.lifecycle_status == "trashed"]
        if batch_id:
            filters.append(FrameAsset.batch_id == batch_id)
        if search.strip():
            filters.append(func.lower(FrameAsset.stored_path).contains(search.strip().lower()))
        with session_scope(registry) as session:
            total = session.scalar(select(func.count()).select_from(FrameAsset).where(*filters)) or 0
            frames = list(session.scalars(select(FrameAsset).where(*filters).order_by(FrameAsset.trashed_at.desc(), FrameAsset.id).offset((page - 1) * page_size).limit(page_size)))
            items = []
            for frame in frames:
                annotation = session.get(AnnotationImageRecord, frame.id)
                items.append({
                    "id": frame.id,
                    "batch_id": frame.batch_id,
                    "filename": Path(frame.stored_path).name,
                    "stored_path": frame.stored_path,
                    "size_bytes": frame.size_bytes,
                    "has_annotation": annotation is not None,
                    "trashed_at": frame.trashed_at,
                    "purge_after": frame.purge_after,
                })
        return {"items": items, "page": page, "page_size": page_size, "total": total}

    @app.get("/api/recycle-bin/summary")
    def recycle_bin_summary() -> dict:
        result = recycle_bin.summary()
        return {"item_count": result.item_count, "total_bytes": result.total_bytes, "earliest_purge_after": result.earliest_purge_after}

    @app.post("/api/recycle-bin/frames/restore")
    def restore_recycled_frames(req: RecycleMutationRequest) -> dict:
        try:
            affected = recycle_bin.restore(req.ids, request_id=req.request_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="recycled image not found") from exc
        return {"affected_count": affected}

    @app.delete("/api/recycle-bin/frames")
    def purge_recycled_frames(req: RecyclePurgeRequest) -> dict:
        if req.confirm_count != len(set(req.ids)):
            raise HTTPException(status_code=422, detail="confirmation count does not match selected images")
        try:
            result = recycle_bin.purge(req.ids, request_id=req.request_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="recycled image not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"deleted_count": result.deleted_count, "released_bytes": result.released_bytes, "failed_keys": list(result.failed_keys)}

    @app.post("/api/recycle-bin/purge-expired")
    def purge_expired_recycled_frames() -> dict:
        result = recycle_bin.purge_expired()
        return {"deleted_count": result.deleted_count, "released_bytes": result.released_bytes, "failed_keys": list(result.failed_keys)}

    def _bulk_frame_selection(job_id: str, args: dict) -> None:
        batch_id = args["batch_id"]
        selection = args["selection"]
        target_status = args["target_status"]
        with session_scope(registry) as session:
            task_id = session.execute(select(VideoCollection.task_id).select_from(FrameBatch).join(VideoCollection, FrameBatch.collection_id == VideoCollection.id).where(FrameBatch.id == batch_id)).scalar_one()
            if selection["mode"] == "explicit":
                filters = [FrameAsset.batch_id == batch_id, FrameAsset.lifecycle_status == "active", FrameAsset.id.in_(selection["ids"])]
            else:
                filters = _frame_filters(batch_id, selection.get("status"), selection.get("search", ""))
                if selection.get("excluded_ids"):
                    filters.append(FrameAsset.id.not_in(selection["excluded_ids"]))
            frames = list(session.scalars(select(FrameAsset).where(*filters).order_by(FrameAsset.id)))
            total = len(frames)
            batch_dir = root / "frame-batches" / task_id / batch_id
            for index, frame in enumerate(frames, start=1):
                source = Path(frame.stored_path)
                if not source.is_absolute():
                    source = root / source
                if target_status == "selected":
                    destination = batch_dir / "selected" / source.name
                    reason = None
                    db_status = "selected"
                elif target_status.startswith("rejected/"):
                    reason = target_status.split("/", 1)[1]
                    destination = batch_dir / "rejected" / reason / source.name
                    db_status = "rejected"
                else:
                    destination = batch_dir / "candidates" / source.name
                    reason = None
                    db_status = "candidate"
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source.resolve() != destination.resolve() and source.exists():
                    shutil.move(source, destination)
                frame.stored_path = destination.as_posix()
                frame.status = db_status
                frame.rejection_reason = reason
                if index % 100 == 0 or index == total:
                    job_tracker.update_job(job_id, progress=(index / max(total, 1)) * 90, message=f"正在更新 {index}/{total} 张图片")
        result = sync_selection(batch_id, root / "frame-batches" / task_id / batch_id, registry)
        job_tracker.update_job(job_id, progress=95, payload={"affected_count": total, "summary": {"candidate": result.candidate, "selected": result.selected, "rejected": result.rejected}})

    @app.post("/api/frame-batches/{batch_id}/bulk-selection", status_code=202)
    def bulk_frame_selection(batch_id: str, req: BulkFrameSelectionRequest) -> dict:
        with session_scope(registry) as session:
            if session.get(FrameBatch, batch_id) is None:
                raise HTTPException(status_code=404, detail="batch not found")
            if req.selection.mode == "explicit":
                filters = [FrameAsset.batch_id == batch_id, FrameAsset.lifecycle_status == "active", FrameAsset.id.in_(req.selection.ids)]
            else:
                filters = _frame_filters(batch_id, req.selection.status, req.selection.search)
                if req.selection.excluded_ids:
                    filters.append(FrameAsset.id.not_in(req.selection.excluded_ids))
            affected_count = session.scalar(select(func.count()).select_from(FrameAsset).where(*filters)) or 0
        if affected_count == 0:
            raise HTTPException(status_code=409, detail="selection matches no frames")
        job_id = job_tracker.start_background_task(_bulk_frame_selection, args={"batch_id": batch_id, "selection": req.selection.model_dump(), "target_status": req.target_status}, message=f"正在批量更新 {affected_count} 张图片")
        return {"job_id": job_id, "affected_count": affected_count}

    @app.get("/api/frame-assets/content")
    def serve_frame_content(path: str) -> FileResponse:
        candidate = (root / path).resolve()
        if root.resolve() not in candidate.parents:
            raise HTTPException(status_code=400, detail="invalid path traversal")
        if not candidate.is_file():
            raise HTTPException(status_code=404, detail="file not found")
        return FileResponse(candidate)

    @app.get("/api/frame-batches/{batch_id}/duplicates", response_model=list[DuplicateGroupSummary])
    def get_batch_duplicates(batch_id: str) -> list[DuplicateGroupSummary]:
        with session_scope(registry) as session:
            task_id = session.execute(
                select(VideoCollection.task_id)
                .select_from(FrameBatch)
                .join(VideoCollection, FrameBatch.collection_id == VideoCollection.id)
                .where(FrameBatch.id == batch_id)
            ).scalar()
        if not task_id:
            raise HTTPException(status_code=404, detail="batch not found")

        candidates_dir = root / "frame-batches" / task_id / batch_id / "candidates"
        if not candidates_dir.exists():
            return []

        paths = [
            p for p in candidates_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        ]
        groups = find_duplicate_groups(paths, 6)
        return [
            DuplicateGroupSummary(
                canonical=Path(g.canonical).relative_to(root).as_posix(),
                duplicates=[Path(d).relative_to(root).as_posix() for d in g.duplicates]
            )
            for g in groups
        ]

    @app.post("/api/frame-batches/{batch_id}/selection")
    def update_frame_selection(batch_id: str, req: SelectionUpdateRequest) -> dict:
        with session_scope(registry) as session:
            task_id = session.execute(
                select(VideoCollection.task_id)
                .select_from(FrameBatch)
                .join(VideoCollection, FrameBatch.collection_id == VideoCollection.id)
                .where(FrameBatch.id == batch_id)
            ).scalar()
        if not task_id:
            raise HTTPException(status_code=404, detail="batch not found")

        batch_dir = root / "frame-batches" / task_id / batch_id
        candidates_dir = batch_dir / "candidates"
        selected_dir = batch_dir / "selected"
        rejected_dir = batch_dir / "rejected"

        selected_dir.mkdir(exist_ok=True)
        rejected_dir.mkdir(exist_ok=True)

        current_locations = {}
        for path in batch_dir.rglob("*.jpg"):
            current_locations[path.name] = path

        for filename, target_status in req.selections.items():
            if filename not in current_locations:
                continue
            src_path = current_locations[filename]
            if target_status == "selected":
                dest_path = selected_dir / filename
            elif target_status.startswith("rejected/"):
                reason = target_status.split("/", 1)[1]
                reason_dir = rejected_dir / reason
                reason_dir.mkdir(parents=True, exist_ok=True)
                dest_path = reason_dir / filename
            else:
                dest_path = candidates_dir / filename

            if src_path != dest_path:
                shutil.move(src_path, dest_path)

        result = sync_selection(batch_id, batch_dir, registry)
        return {
            "candidate": result.candidate,
            "selected": result.selected,
            "rejected": result.rejected,
            "duplicate": result.duplicate,
            "manifest_path": result.manifest_path.relative_to(root).as_posix()
        }

    @app.post("/api/frame-batches/{batch_id}/annotation-package")
    def create_package(batch_id: str) -> dict:
        with session_scope(registry) as session:
            task_id = session.execute(
                select(VideoCollection.task_id)
                .select_from(FrameBatch)
                .join(VideoCollection, FrameBatch.collection_id == VideoCollection.id)
                .where(FrameBatch.id == batch_id)
            ).scalar()
        if not task_id:
            raise HTTPException(status_code=404, detail="batch not found")

        package_dir = root / "annotation-packages" / task_id
        package_dir.mkdir(parents=True, exist_ok=True)
        output_zip = package_dir / f"{batch_id}.zip"

        result = build_roboflow_package(task_id, batch_id, output_zip, registry)
        return {
            "sha256": result.sha256,
            "path": str(output_zip.relative_to(root).as_posix()),
            "download_url": f"/api/annotation-packages/{batch_id}/download"
        }

    @app.get("/api/annotation-packages/{batch_id}/download")
    def download_package(batch_id: str) -> FileResponse:
        with session_scope(registry) as session:
            task_id = session.execute(
                select(VideoCollection.task_id)
                .select_from(FrameBatch)
                .join(VideoCollection, FrameBatch.collection_id == VideoCollection.id)
                .where(FrameBatch.id == batch_id)
            ).scalar()
        if not task_id:
            raise HTTPException(status_code=404, detail="batch not found")

        output_zip = root / "annotation-packages" / task_id / f"{batch_id}.zip"
        if not output_zip.is_file():
            raise HTTPException(status_code=404, detail="package file not found")
        return FileResponse(output_zip, media_type="application/zip", filename=f"{batch_id}.zip")

    @app.post("/api/annotation-imports")
    def import_annotations(req: AnnotationImportRequest) -> dict:
        from yolo_factory.annotations.import_service import import_roboflow_export

        task_config = resolve_task_config(req.task_id)
        if not task_config:
            raise HTTPException(status_code=404, detail=f"task config for {req.task_id} not found")

        archive_path = require_path_within(
            Path(req.archive_path),
            root / "imports",
            "annotation archive must be inside the managed imports directory",
        )
        if not archive_path.is_file():
            raise HTTPException(status_code=404, detail="annotation archive not found")
        result = import_roboflow_export(
            archive_path,
            task_config,
            req.project,
            req.provider_version,
            root,
            registry
        )
        return {
            "import_id": result.import_id,
            "extracted_root": str(result.extracted_root.relative_to(root).as_posix()),
            "sample_count": result.sample_count
        }

    @app.post("/api/annotation-imports/upload", status_code=201)
    async def upload_annotation_import(
        task_id: str = Form(...),
        project: str = Form(...),
        provider_version: str = Form(...),
        file: UploadFile = File(...),
    ) -> dict:
        filename = safe_upload_name(file, {".zip"}, "annotation archive")
        staging_dir = root / "imports" / "annotation-uploads" / uuid.uuid4().hex
        destination = staging_dir / filename
        try:
            if await save_uploaded_file(file, destination) == 0:
                raise HTTPException(status_code=422, detail="annotation archive is empty")
            return import_annotations(
                AnnotationImportRequest(
                    task_id=task_id,
                    archive_path=str(destination.resolve()),
                    project=project,
                    provider_version=provider_version,
                )
            )
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)

    @app.post("/api/dataset-releases")
    @heavy_operation("dataset-release")
    def release_new_dataset(req: DatasetReleaseRequest) -> dict:
        from yolo_factory.datasets.release import release_dataset
        from yolo_factory.integrations.dvc import DvcAdapter

        task_config = resolve_task_config(req.task_id)
        if not task_config:
            raise HTTPException(status_code=404, detail=f"task config for {req.task_id} not found")

        try:
            result = release_dataset(
                task_config,
                req.annotation_import_id,
                req.version,
                root,
                registry,
                DvcAdapter(root),
                display_name=req.display_name,
                split_ratios=req.split_ratios.model_dump(),
                split_seed=req.split_seed,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {
            "release_id": result.release_id,
            "release_path": str(result.release_path.relative_to(root).as_posix())
        }

    return app
