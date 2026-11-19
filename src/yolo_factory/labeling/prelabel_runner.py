from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path

from yolo_factory.labeling.predictions import extract_detections


def run(manifest_path: Path, output_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    model_path = manifest["model_path"]
    task_type = manifest["task_type"]
    imgsz = int(manifest.get("imgsz", 640))
    confidence = float(manifest.get("confidence", 0.25))
    iou = float(manifest.get("iou", 0.7))
    frames = manifest.get("frames", [])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8", newline="\n") as stream:
        from ultralytics import YOLO

        try:
            model = YOLO(model_path, task=task_type)
        except Exception as exc:
            stream.write(json.dumps({
                "status": "error",
                "error": f"model load failed: {exc}",
                "traceback": traceback.format_exc(),
            }, ensure_ascii=False) + "\n")
            stream.flush()
            return 1
        for frame in frames:
            frame_id = frame["frame_id"]
            try:
                result = model.predict(
                    frame["image_path"],
                    imgsz=imgsz,
                    conf=confidence,
                    iou=iou,
                    verbose=False,
                )[0]
                detections = extract_detections(result, task_type)
                names = result.names
                if not isinstance(names, dict):
                    names = {index: str(name) for index, name in enumerate(names)}
                payload = {
                    "status": "ok",
                    "frame_id": frame_id,
                    "detections": detections,
                    "names": {int(key): str(value) for key, value in names.items()},
                }
            except Exception as exc:
                payload = {
                    "status": "error",
                    "frame_id": frame_id,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
            stream.flush()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch pre-label frames with a YOLO model.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    return run(Path(args.manifest), Path(args.output))


if __name__ == "__main__":
    raise SystemExit(main())
