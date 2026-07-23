import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


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


def prediction_source(manifest: dict):
    if manifest["mode"] in {"image", "video"}:
        return manifest["sources"][0]
    return manifest["sources"]


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
    results = model.predict(
        source=prediction_source(manifest),
        conf=manifest["confidence"],
        device=manifest["device"],
        save=True,
        project=str(output_directory),
        name="annotated",
        exist_ok=True,
        stream=manifest["mode"] == "video",
        verbose=False,
    )
    normalized = []
    for index, result in enumerate(results):
        normalized.append({"index": index, "source": str(result.path), "detections": _detections(result), "speed": result.speed})
        _emit(progress_path, "running", min(95, 15 + index), f"Processed {index + 1} item(s)")
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
    manifest = parser.parse_args().manifest
    try:
        return run(manifest)
    except Exception as exc:
        _emit(manifest.parent / "progress.jsonl", "failed", 100, f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
