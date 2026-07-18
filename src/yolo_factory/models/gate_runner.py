import argparse
import json
import platform
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml

from yolo_factory.models.gates import box_iou, file_metadata

SUPPORTED_IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}


def _samples(data_yaml: Path, limit: int = 3) -> list[str]:
    payload = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("data.yaml must contain a mapping")

    root_value = payload.get("path", ".")
    if not isinstance(root_value, str):
        raise ValueError("data.yaml 'path' must be a string")

    val_value = payload.get("val")
    test_value = payload.get("test")
    split_value = val_value if val_value is not None and val_value != "" else test_value
    if split_value is None or split_value == "":
        raise ValueError("data.yaml must define a non-empty 'val' or 'test' split path")
    if not isinstance(split_value, str):
        raise ValueError("data.yaml 'val' or 'test' split path must be a string")
    if not split_value.strip():
        raise ValueError("data.yaml must define a non-empty 'val' or 'test' split path")

    root = (data_yaml.parent / root_value).resolve()
    image_root = (root / split_value).resolve()
    if not image_root.is_dir():
        raise ValueError(f"dataset split directory does not exist: {image_root}")

    samples = [
        str(path)
        for path in sorted(image_root.iterdir())
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS
    ]
    if not samples:
        raise ValueError(f"dataset split directory contains no supported images: {image_root}")
    return samples[:limit]


def _normalize(result) -> list[dict]:
    boxes = result.boxes
    if boxes is None:
        return []
    xyxy = boxes.xyxy.detach().cpu().numpy()
    confidences = boxes.conf.detach().cpu().numpy()
    classes = boxes.cls.detach().cpu().numpy()
    masks = result.masks.data.detach().cpu().numpy() if result.masks is not None else None
    normalized = []
    for index in range(len(xyxy)):
        normalized.append({
            "class_id": int(classes[index]),
            "confidence": float(confidences[index]),
            "box": [float(value) for value in xyxy[index]],
            "mask": masks[index] if masks is not None and index < len(masks) else None,
        })
    return normalized


def _mask_iou(left: np.ndarray | None, right: np.ndarray | None) -> float | None:
    if left is None and right is None:
        return None
    if left is None or right is None:
        return 0.0
    if left.shape != right.shape:
        right = cv2.resize(right.astype(np.float32), (left.shape[1], left.shape[0]), interpolation=cv2.INTER_NEAREST)
    left_binary = left > 0.5
    right_binary = right > 0.5
    union = np.logical_or(left_binary, right_binary).sum()
    return float(np.logical_and(left_binary, right_binary).sum() / union) if union else 1.0


def _compare(pt_items: list[dict], onnx_items: list[dict], task_type: str) -> dict:
    unmatched = list(range(len(onnx_items)))
    pairs = []
    for pt_item in pt_items:
        candidates = [index for index in unmatched if onnx_items[index]["class_id"] == pt_item["class_id"]]
        if not candidates:
            continue
        best = max(candidates, key=lambda index: box_iou(pt_item["box"], onnx_items[index]["box"]))
        onnx_item = onnx_items[best]
        pair = {
            "class_id": pt_item["class_id"],
            "box_iou": box_iou(pt_item["box"], onnx_item["box"]),
            "confidence_delta": abs(pt_item["confidence"] - onnx_item["confidence"]),
        }
        if task_type == "segment":
            pair["mask_iou"] = _mask_iou(pt_item["mask"], onnx_item["mask"])
        pair["passed"] = pair["box_iou"] >= 0.8 and pair["confidence_delta"] <= 0.15 and (task_type != "segment" or pair["mask_iou"] is not None and pair["mask_iou"] >= 0.75)
        if pair["passed"]:
            unmatched.remove(best)
        pairs.append(pair)
    passed = len(pt_items) == len(onnx_items) == sum(1 for pair in pairs if pair["passed"])
    return {"passed": passed, "pt_count": len(pt_items), "onnx_count": len(onnx_items), "pairs": pairs}


def run(manifest_path: Path) -> int:
    from ultralytics import YOLO
    import torch
    import ultralytics

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pt_path = Path(manifest["pt_path"]).resolve()
    data_yaml = Path(manifest["data_yaml_path"]).resolve()
    output = manifest_path.parent / "result.json"
    pt_model = YOLO(str(pt_path))
    exported = pt_model.export(format="onnx", imgsz=manifest["image_size"], opset=17, dynamic=False, simplify=True)
    onnx_path = Path(exported).resolve()
    onnx_model = YOLO(str(onnx_path), task=manifest["task_type"])
    sample_reports = []
    for source in _samples(data_yaml):
        pt_result = pt_model.predict(source=source, imgsz=manifest["image_size"], conf=0.25, max_det=100, device=manifest["device"], verbose=False)[0]
        onnx_result = onnx_model.predict(source=source, imgsz=manifest["image_size"], conf=0.25, max_det=100, device="cpu", verbose=False)[0]
        sample_reports.append({"source": source, **_compare(_normalize(pt_result), _normalize(onnx_result), manifest["task_type"])})
    consistency_passed = bool(sample_reports) and all(report["passed"] for report in sample_reports)
    result = {
        "passed": consistency_passed,
        "gates": {"training": True, "pt": True, "onnx": onnx_path.is_file(), "consistency": consistency_passed},
        "artifacts": {"pt": file_metadata(pt_path), "onnx": file_metadata(onnx_path)},
        "environment": {"python": platform.python_version(), "torch": torch.__version__, "cuda": str(torch.version.cuda), "ultralytics": ultralytics.__version__},
        "samples": sample_reports,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["passed"] else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    return run(parser.parse_args().manifest)


if __name__ == "__main__":
    raise SystemExit(main())
