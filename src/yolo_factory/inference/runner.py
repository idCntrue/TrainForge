import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ONNX_RAW_PREVIEW_LIMIT = 256


def _emit(path: Path, status: str, progress: float, message: str) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps({"status": status, "progress": progress, "message": message, "timestamp": datetime.now(timezone.utc).isoformat()}, sort_keys=True) + "\n")


def _detections(result) -> list[dict]:
    boxes = result.boxes
    if boxes is None:
        return []
    xyxy = boxes.xyxy.detach().cpu().numpy()
    confidence = boxes.conf.detach().cpu().numpy()
    classes = boxes.cls.detach().cpu().numpy()
    names = result.names
    masks = result.masks.xyn if result.masks is not None else None
    detections = []
    for index in range(len(xyxy)):
        class_id = int(classes[index])
        item = {
            "class_id": class_id,
            "class_name": names[class_id],
            "confidence": float(confidence[index]),
            "box": [float(value) for value in xyxy[index]],
        }
        if masks is not None and index < len(masks):
            item["polygon"] = [float(value) for point in masks[index] for value in point]
        detections.append(item)
    return detections


def _onnx_tensor_summary(name: str, tensor, *, preview_limit: int = ONNX_RAW_PREVIEW_LIMIT) -> dict:
    values = np.asarray(tensor)
    flattened = values.reshape(-1)
    preview = []
    for value in flattened[:preview_limit]:
        number = float(value)
        preview.append(number if np.isfinite(number) else None)
    finite_values = flattened[np.isfinite(flattened)]
    return {
        "name": name,
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "elements": int(values.size),
        "min": float(finite_values.min()) if finite_values.size else None,
        "max": float(finite_values.max()) if finite_values.size else None,
        "preview": preview,
    }


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "numpy"):
        value = value.numpy()
    return np.asarray(value)


def _predictor_input_tensor(predictor) -> np.ndarray:
    input_tensor = getattr(predictor, "im", None)
    if input_tensor is None:
        batch = getattr(predictor, "batch", None)
        if not isinstance(batch, tuple) or len(batch) < 2:
            raise RuntimeError("Ultralytics predictor did not retain an input batch")
        input_tensor = predictor.preprocess(batch[1])
    return _as_numpy(input_tensor)


def _capture_onnx_output(predictor) -> dict:
    model = getattr(predictor, "model", None)
    session = getattr(model, "session", None) or getattr(getattr(model, "backend", None), "session", None)
    if session is None:
        raise RuntimeError("ONNX Runtime session is unavailable")
    input_nodes = session.get_inputs()
    if not input_nodes:
        raise RuntimeError("ONNX Runtime session has no input nodes")
    input_name = input_nodes[0].name
    input_tensor = _predictor_input_tensor(predictor)
    output_nodes = session.get_outputs()
    output_values = session.run(None, {input_name: input_tensor})
    return {
        "input": {"name": input_name, "shape": list(input_tensor.shape), "dtype": str(input_tensor.dtype)},
        "outputs": [
            _onnx_tensor_summary(node.name, output)
            for node, output in zip(output_nodes, output_values, strict=True)
        ],
        "preview_limit": ONNX_RAW_PREVIEW_LIMIT,
    }


def _raw_onnx_diagnostic(runtime: str, predictor) -> dict:
    if runtime != "onnx":
        return {"raw_onnx_output_error": "原始 ONNX 输出仅适用于 ONNX Runtime 推理"}
    try:
        return {"raw_onnx_output": _capture_onnx_output(predictor)}
    except Exception as error:
        return {"raw_onnx_output_error": str(error)}


def prediction_source(manifest: dict):
    if manifest["mode"] in {"image", "video"}:
        return manifest["sources"][0]
    return manifest["sources"]


def prediction_inputs(manifest: dict) -> list:
    if manifest["mode"] == "batch" and manifest["runtime"] == "onnx":
        return list(manifest["sources"])
    return [prediction_source(manifest)]


def media_for_source(source: str, media: list[str]) -> str | None:
    stem = Path(source).stem
    return next((path for path in media if Path(path).stem == stem), None)


def ensure_browser_compatible_video(
    media: list[str],
    *,
    ffmpeg_executable: str | None = None,
    run_command=subprocess.run,
) -> list[str]:
    if not media:
        return media
    source = Path(media[0])
    if source.suffix.lower() == ".mp4":
        return media
    ffmpeg = ffmpeg_executable or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required to create a browser-compatible inference video")
    destination = source.with_suffix(".mp4")
    run_command([
        ffmpeg, "-y", "-i", str(source), "-an", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(destination),
    ], check=True, capture_output=True, text=True)
    if not destination.is_file():
        raise RuntimeError("FFmpeg completed without creating the inference MP4")
    source.unlink()
    return [str(destination.resolve())]


def run(manifest_path: Path) -> int:
    from ultralytics import YOLO

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    progress_path = manifest_path.parent / "progress.jsonl"
    _emit(progress_path, "running", 5, "Loading model")
    output_directory = manifest_path.parent / "outputs"
    output_directory.mkdir()
    model = YOLO(manifest["artifact_path"], task=manifest["task_type"])
    _emit(progress_path, "running", 10, "Model loaded; inference started")
    normalized = []
    total_sources = len(manifest["sources"])
    for source in prediction_inputs(manifest):
        source_start = len(normalized)
        results = model.predict(
            source=source,
            conf=manifest["confidence"],
            device=manifest["device"],
            save=True,
            project=str(output_directory),
            name="annotated",
            exist_ok=True,
            stream=manifest["mode"] == "video",
            verbose=False,
        )
        for result in results:
            index = len(normalized)
            normalized.append({"index": index, "source": str(result.path), "detections": _detections(result), "speed": result.speed})
            progress = min(95, 10 + (85 * (index + 1) / max(1, total_sources)))
            _emit(progress_path, "running", progress, f"Processed {index + 1} item(s)")
        diagnostic = _raw_onnx_diagnostic(manifest["runtime"], getattr(model, "predictor", None))
        for item in normalized[source_start:]:
            item.update(diagnostic)
    media = sorted(str(path.resolve()) for path in (output_directory / "annotated").rglob("*") if path.is_file())
    if manifest["mode"] == "video":
        media = ensure_browser_compatible_video(media)
    else:
        for item in normalized:
            item["media_path"] = media_for_source(item["source"], media)
    payload = {"run_id": manifest["run_id"], "runtime": manifest["runtime"], "mode": manifest["mode"], "items": normalized, "media": media}
    result_path = manifest_path.parent / "result.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _emit(progress_path, "completed", 100, f"Completed {len(normalized)} item(s)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--process-token")
    manifest = parser.parse_args().manifest
    try:
        return run(manifest)
    except Exception as exc:
        _emit(manifest.parent / "progress.jsonl", "failed", 100, f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
