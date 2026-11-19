from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from yolo_factory.annotations.repository import AnnotationRepository
from yolo_factory.common.task_metadata import decode_task_classes
from yolo_factory.labeling.mapping import ClassMapping, build_class_mapping
from yolo_factory.labeling.repository import PrelabelRunRepository
from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import (
    AnnotationImageRecord,
    AnnotationShapeRecord,
    FrameAsset,
    FrameBatch,
    Task,
    VideoCollection,
)


class PrelabelError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedLabelModel:
    source: str
    name: str
    task_type: str
    path: str
    classes: tuple[str, ...]
    aliases: dict[str, str]

    def as_dict(self) -> dict:
        return {
            "model_source": self.source,
            "name": self.name,
            "task_type": self.task_type,
            "classes": list(self.classes),
        }


@dataclass(frozen=True)
class PrelabelFrame:
    frame_id: str
    image_path: str


class PrelabelService:
    def __init__(
        self,
        *,
        registry: Registry,
        storage_root: Path,
        job_tracker,
        annotation_repository: AnnotationRepository,
        model_repository,
        imported_model_repository,
        run_repository: PrelabelRunRepository,
        python_executable: str | None = None,
        runner_factory=None,
    ) -> None:
        self._registry = registry
        self._root = storage_root
        self._jobs = job_tracker
        self._annotations = annotation_repository
        self._models = model_repository
        self._imported = imported_model_repository
        self._runs = run_repository
        self._python = python_executable or sys.executable
        self._runner_factory = runner_factory
        self._lock = threading.Lock()
        self._active_run_id: str | None = None
        self._process: subprocess.Popen | None = None
        self._cancel = threading.Event()

    # ---------------------------------------------------------------- models
    def resolve_model(self, model_source: str) -> ResolvedLabelModel:
        source = model_source.strip()
        if source.startswith("model_version:") or source.startswith("model:"):
            model_id = source.split(":", 1)[1]
            model = self._models.get(model_id)
            if model is None:
                raise PrelabelError(f"模型版本不存在: {model_id}")
            if model.status != "published":
                raise PrelabelError("只能使用已发布的模型版本，请先在模型页发布")
            artifacts = model.artifacts or {}
            path = (artifacts.get("pt") or {}).get("path") or (artifacts.get("onnx") or {}).get("path")
            if not path:
                raise PrelabelError("该模型没有可用的权重文件")
            if not Path(path).is_file():
                raise PrelabelError(f"模型权重文件不存在: {path}")
            return ResolvedLabelModel(
                source=f"model_version:{model.id}",
                name=f"{model.spec.name} v{model.spec.version}",
                task_type=model.spec.task_type,
                path=path,
                classes=tuple(model.spec.selected_classes),
                aliases=dict(model.spec.class_aliases or {}),
            )
        if source.startswith("imported_model:"):
            model_id = source.split(":", 1)[1]
            model = self._imported.get(model_id)
            if model is None:
                raise PrelabelError(f"导入模型不存在: {model_id}")
            if model.status != "ready":
                raise PrelabelError("导入模型尚未就绪")
            if not Path(model.artifact_path).is_file():
                raise PrelabelError(f"模型权重文件不存在: {model.artifact_path}")
            return ResolvedLabelModel(
                source=f"imported_model:{model.id}",
                name=model.name,
                task_type=model.task_type,
                path=model.artifact_path,
                classes=tuple(model.class_names),
                aliases={},
            )
        raise PrelabelError("模型标识格式应为 model_version:<id> 或 imported_model:<id>")

    def list_label_models(self, task_id: str) -> list[dict]:
        with session_scope(self._registry) as session:
            task = session.get(Task, task_id)
            if task is None:
                raise KeyError(task_id)
            classes, _ = decode_task_classes(task.classes_json)
        items: list[dict] = []
        for model in self._models.list(status="published"):
            mapping = build_class_mapping(dict(enumerate(model.spec.selected_classes)), classes, model.spec.class_aliases)
            if model.spec.task_type != task.task_type:
                continue
            items.append({
                "model_source": f"model_version:{model.id}",
                "name": f"{model.spec.name} v{model.spec.version}",
                "task_type": model.spec.task_type,
                "published_at": model.published_at.isoformat() if model.published_at else None,
                "mapped_classes": len(mapping.class_ids),
                "unmapped_classes": list(mapping.unmapped),
                "classes": list(model.spec.selected_classes),
            })
        for model in self._imported.list():
            if model.status != "ready":
                continue
            mapping = build_class_mapping(list(model.class_names), classes)
            if model.task_type != task.task_type:
                continue
            items.append({
                "model_source": f"imported_model:{model.id}",
                "name": model.name,
                "task_type": model.task_type,
                "published_at": model.created_at.isoformat(),
                "mapped_classes": len(mapping.class_ids),
                "unmapped_classes": list(mapping.unmapped),
                "classes": list(model.class_names),
            })
        return items

    # ----------------------------------------------------------------- start
    def start(self, batch_id: str, *, model_source: str, confidence: float = 0.25, iou: float = 0.7, overwrite: bool = False) -> dict:
        model = self.resolve_model(model_source)
        with session_scope(self._registry) as session:
            batch = session.get(FrameBatch, batch_id)
            if batch is None:
                raise PrelabelError(f"批次不存在: {batch_id}")
            collection = session.get(VideoCollection, batch.collection_id)
            if collection is None:
                raise PrelabelError("批次所属集合不存在")
            task = session.get(Task, collection.task_id)
            if task is None:
                raise PrelabelError("批次所属任务不存在")
            task_id, task_type = task.id, task.task_type
            classes, _ = decode_task_classes(task.classes_json)
        if model.task_type != task_type:
            raise PrelabelError(f"模型类型 {model.task_type} 与任务类型 {task_type} 不一致")

        self._annotations.sync_selected_frames(task_id)
        frames, skipped = self._candidate_frames(batch_id, task_id, overwrite=overwrite)
        if not frames:
            raise PrelabelError("没有可预标注的图片：批次中的图片可能已标注或已审核")

        with self._lock:
            if self._active_run_id is not None:
                raise PrelabelError("已有预标注任务在运行，请等待完成或取消")
            job_id = self._jobs.create_job("模型预标注排队中")
            run_id = f"prelabel-{uuid.uuid4().hex}"
            self._runs.create(
                run_id=run_id, job_id=job_id, batch_id=batch_id, task_id=task_id,
                model_source=model.source, model_name=model.name,
                confidence=confidence, iou=iou, frames_total=len(frames),
            )
            self._active_run_id = run_id
            self._cancel.clear()
        thread = threading.Thread(
            target=self._execute,
            args=(run_id, job_id, model, task_type, classes, frames, skipped, confidence, iou),
            name=f"prelabel-{run_id}",
            daemon=True,
        )
        thread.start()
        return {"run_id": run_id, "job_id": job_id, "frames_total": len(frames), "frames_skipped": skipped}

    def _candidate_frames(self, batch_id: str, task_id: str, *, overwrite: bool) -> tuple[list[PrelabelFrame], int]:
        with session_scope(self._registry) as session:
            frame_ids = list(session.scalars(
                select(FrameAsset.id).where(
                    FrameAsset.batch_id == batch_id,
                    FrameAsset.lifecycle_status == "active",
                )
            ))
            if not frame_ids:
                return [], 0
            images = list(session.scalars(
                select(AnnotationImageRecord).where(
                    AnnotationImageRecord.frame_id.in_(frame_ids),
                    AnnotationImageRecord.task_id == task_id,
                    AnnotationImageRecord.status != "reviewed",
                )
            ))
            existing = set(session.scalars(
                select(AnnotationShapeRecord.frame_id).where(
                    AnnotationShapeRecord.frame_id.in_([image.frame_id for image in images]),
                    AnnotationShapeRecord.status != "rejected",
                )
            )) if images else set()
            confirmed_frames = set(session.scalars(
                select(AnnotationShapeRecord.frame_id).where(
                    AnnotationShapeRecord.frame_id.in_([image.frame_id for image in images]),
                    AnnotationShapeRecord.status == "confirmed",
                )
            )) if images else set()
            draft_frames: list[str] = []
            if overwrite and existing:
                draft_frames = list(session.scalars(
                    select(AnnotationShapeRecord.frame_id).where(
                        AnnotationShapeRecord.frame_id.in_([image.frame_id for image in images]),
                        AnnotationShapeRecord.status == "draft",
                    )
                ))
            frames = [
                PrelabelFrame(frame_id=image.frame_id, image_path=image.image_path)
                for image in images
                if image.frame_id not in confirmed_frames
                and (overwrite or image.frame_id not in existing)
            ]
            skipped = len(images) - len(frames)
        if draft_frames:
            self._reject_drafts(draft_frames)
        return frames, skipped

    def _reject_drafts(self, frame_ids: list[str]) -> None:
        from sqlalchemy import update

        from yolo_factory.registry.models import AnnotationImageRecord as ImageRecord
        from yolo_factory.registry.models import AnnotationShapeRecord as Shape
        with session_scope(self._registry) as session:
            session.execute(
                update(Shape)
                .where(Shape.frame_id.in_(frame_ids), Shape.status == "draft")
                .values(status="rejected")
            )
            session.execute(
                update(ImageRecord)
                .where(ImageRecord.frame_id.in_(frame_ids))
                .values(revision=ImageRecord.revision + 1)
            )

    # -------------------------------------------------------------- execution
    def _execute(self, run_id: str, job_id: str, model: ResolvedLabelModel, task_type: str, classes: list[str], frames: list[PrelabelFrame], skipped: int, confidence: float, iou: float) -> None:
        directory = self._root / "prelabel-runs" / run_id
        directory.mkdir(parents=True, exist_ok=True)
        manifest_path = directory / "manifest.json"
        output_path = directory / "detections.jsonl"
        log_path = directory / "runner.log"
        manifest_path.write_text(json.dumps({
            "model_path": model.path,
            "task_type": task_type,
            "imgsz": 640,
            "confidence": confidence,
            "iou": iou,
            "frames": [{"frame_id": frame.frame_id, "image_path": frame.image_path} for frame in frames],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        output_path.unlink(missing_ok=True)
        process = None
        mapping: ClassMapping | None = None
        unmapped: set[str] = set()
        processed = 0
        shapes_created = 0
        errors = 0
        status = "completed"
        message = ""
        log_stream = log_path.open("ab")
        try:
            self._jobs.update_job(job_id, status="running", progress=0.02, message=f"正在加载模型 {model.name}")
            if self._runner_factory is not None:
                process = self._runner_factory(manifest_path, output_path)
            else:
                process = subprocess.Popen(
                    [
                        self._python, "-m", "yolo_factory.labeling.prelabel_runner",
                        "--manifest", str(manifest_path),
                        "--output", str(output_path),
                    ],
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                )
            self._process = process
            processed_lines = 0

            def consume(line: str) -> None:
                nonlocal mapping, processed, shapes_created, errors, status, message
                try:
                    parsed = self._handle_line(
                        line, mapping, unmapped, task_type, classes,
                        model, job_id, confidence, iou,
                    )
                except Exception as exc:
                    errors += 1
                    processed += 1
                    message = f"写入草稿失败: {exc}"
                    return
                if parsed is None:
                    return
                if parsed == "fatal":
                    status = "failed"
                    message = "模型加载失败，请查看预标注日志"
                    return
                mapping, added, error = parsed
                processed += 1
                shapes_created += added
                if error:
                    errors += 1
                progress = 0.05 + 0.93 * processed / max(1, len(frames))
                self._jobs.update_job(
                    job_id,
                    progress=min(0.98, progress),
                    message=f"已处理 {processed}/{len(frames)} 张，生成 {shapes_created} 个草稿框",
                )
                if processed % 5 == 0 or processed == len(frames):
                    self._runs.update(
                        run_id, frames_processed=processed,
                        shapes_created=shapes_created, frames_skipped=skipped + errors,
                        unmapped_classes=sorted(unmapped),
                    )

            while True:
                if self._cancel.is_set():
                    status = "cancelled"
                    self._terminate(process)
                    break
                lines = self._complete_lines(output_path)
                if len(lines) > processed_lines:
                    for line in lines[processed_lines:]:
                        consume(line)
                    processed_lines = len(lines)
                    continue
                if process.poll() is not None:
                    lines = self._complete_lines(output_path)
                    for line in lines[processed_lines:]:
                        consume(line)
                    processed_lines = len(lines)
                    break
                time.sleep(0.25)
            if status == "completed":
                exit_code = process.poll()
                if exit_code not in (0, None):
                    status = "failed"
                    message = f"预标注进程退出码 {exit_code}，请查看日志"
            if status == "completed" and processed == 0:
                status = "failed"
                message = "没有任何图片完成推理"
            if status == "completed":
                message = f"完成：{processed} 张图片，生成 {shapes_created} 个草稿框"
        except Exception as exc:
            status = "failed"
            message = f"预标注失败: {exc}"
        finally:
            log_stream.close()
            self._process = None
            with self._lock:
                self._active_run_id = None
            self._runs.update(
                run_id, status=status, frames_processed=processed, shapes_created=shapes_created,
                frames_skipped=skipped + errors, unmapped_classes=sorted(unmapped),
                error=None if status == "completed" else message,
                finished_at=datetime.now(timezone.utc),
            )
            self._jobs.update_job(
                job_id,
                status="completed" if status == "completed" else ("cancelled" if status == "cancelled" else "failed"),
                progress=1.0 if status == "completed" else None,
                message=message or status,
                payload={
                    "run_id": run_id,
                    "status": status,
                    "frames_processed": processed,
                    "frames_skipped": skipped + errors,
                    "shapes_created": shapes_created,
                    "unmapped_classes": sorted(unmapped),
                    "model_source": model.source,
                    "model_name": model.name,
                },
            )

    @staticmethod
    def _complete_lines(path: Path) -> list[str]:
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
        if text and not text.endswith("\n"):
            text = text.rsplit("\n", 1)[0]
        return text.splitlines()

    def _handle_line(self, line: str, mapping: ClassMapping | None, unmapped: set[str], task_type: str, classes: list[str], model: ResolvedLabelModel, job_id: str, confidence: float, iou: float):
        if not line.strip():
            return None
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return None
        if payload.get("status") == "error" and not payload.get("frame_id"):
            return "fatal"
        if mapping is None and payload.get("names"):
            names = {int(key): str(value) for key, value in payload["names"].items()}
            mapping = build_class_mapping(names, classes, model.aliases)
            unmapped.update(mapping.unmapped)
        if payload.get("status") != "ok" or mapping is None:
            return mapping, 0, True
        mapped: list[dict] = []
        for detection in payload.get("detections", []):
            item = mapping.map_detection(detection)
            if item is None:
                continue
            mapped.append(item)
        added = 0
        if mapped:
            added = self._annotations.create_draft_shapes(
                payload["frame_id"],
                mapped,
                model_source=model.source,
                prelabel_job_id=job_id,
            )
        return mapping, added, False

    def _terminate(self, process) -> None:
        if process is None:
            return
        try:
            if hasattr(process, "terminate"):
                process.terminate()
            if hasattr(process, "wait"):
                process.wait(timeout=10)
        except Exception:
            pass

    def cancel(self, run_id: str) -> None:
        with self._lock:
            if self._active_run_id != run_id:
                raise PrelabelError("该预标注任务不在运行中")
            self._cancel.set()
            process = self._process
        self._terminate(process)

    def is_active(self, run_id: str) -> bool:
        return self._active_run_id == run_id

    def has_active_run(self) -> bool:
        return self._active_run_id is not None
