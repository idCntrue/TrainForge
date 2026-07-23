import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

import cv2
import numpy as np
import yaml
from scipy.optimize import linear_sum_assignment

from yolo_factory.models.gates import box_iou, file_metadata

SUPPORTED_IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}


def _export_onnx_isolated(
    pt_path: Path,
    attempt_directory: Path,
    image_size: int,
    *,
    model_loader=None,
) -> Path:
    if model_loader is None:
        from ultralytics import YOLO

        model_loader = YOLO
    export_directory = (attempt_directory / "exported").resolve()
    export_directory.mkdir(parents=True, exist_ok=True)
    local_pt = export_directory / "source.pt"
    shutil.copy2(pt_path, local_pt)
    try:
        exported = Path(model_loader(str(local_pt)).export(
            format="onnx", imgsz=image_size, opset=17, dynamic=False, simplify=True,
        )).resolve()
        if not exported.is_relative_to(export_directory):
            raise ValueError("gate ONNX export escaped the attempt directory")
        if not exported.is_file():
            raise ValueError("gate ONNX export did not create an artifact")
        return exported
    finally:
        local_pt.unlink(missing_ok=True)


def _samples(data_yaml: Path, limit: int = 5) -> list[str]:
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
    if len(samples) <= limit:
        return samples
    indices = np.rint(np.linspace(0, len(samples) - 1, limit)).astype(int)
    return [samples[index] for index in indices]


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
    assignments: list[tuple[int, int]] = []
    class_ids = sorted({item["class_id"] for item in pt_items} | {item["class_id"] for item in onnx_items})
    for class_id in class_ids:
        pt_indices = [index for index, item in enumerate(pt_items) if item["class_id"] == class_id]
        onnx_indices = [index for index, item in enumerate(onnx_items) if item["class_id"] == class_id]
        if not pt_indices or not onnx_indices:
            continue
        scores = np.zeros((len(pt_indices), len(onnx_indices)), dtype=np.float64)
        for row, pt_index in enumerate(pt_indices):
            for column, onnx_index in enumerate(onnx_indices):
                box_score = box_iou(pt_items[pt_index]["box"], onnx_items[onnx_index]["box"])
                mask_score = _mask_iou(pt_items[pt_index]["mask"], onnx_items[onnx_index]["mask"])
                scores[row, column] = box_score if task_type != "segment" or mask_score is None else (box_score + mask_score) / 2
        rows, columns = linear_sum_assignment(-scores)
        assignments.extend((pt_indices[row], onnx_indices[column]) for row, column in zip(rows, columns))

    pairs = []
    for pt_index, onnx_index in sorted(assignments):
        pt_item = pt_items[pt_index]
        onnx_item = onnx_items[onnx_index]
        pair = {
            "pt_index": pt_index,
            "onnx_index": onnx_index,
            "class_id": pt_item["class_id"],
            "box_iou": box_iou(pt_item["box"], onnx_item["box"]),
            "confidence_delta": abs(pt_item["confidence"] - onnx_item["confidence"]),
        }
        if task_type == "segment":
            pair["mask_iou"] = _mask_iou(pt_item["mask"], onnx_item["mask"])
            pair["mask_passed"] = pair["mask_iou"] is not None and pair["mask_iou"] >= 0.75
        pair["passed"] = pair["box_iou"] >= 0.8 and pair["confidence_delta"] <= 0.15
        pairs.append(pair)
    passed = len(pt_items) == len(onnx_items) == sum(1 for pair in pairs if pair["passed"])
    mask_consistency = task_type != "segment" or all(pair.get("mask_passed", False) for pair in pairs)
    return {
        "passed": passed,
        "mask_consistency": mask_consistency,
        "pt_count": len(pt_items),
        "onnx_count": len(onnx_items),
        "pairs": pairs,
    }


def _write_comparison_overlay(
    source: Path,
    pt_items: list[dict],
    onnx_items: list[dict],
    pairs: list[dict],
    output: Path,
) -> None:
    image = cv2.imread(str(source))
    if image is None:
        raise ValueError(f"unable to read gate sample image: {source}")
    height, width = image.shape[:2]
    overlay = image.copy()
    for pair in pairs:
        if pair["passed"]:
            continue
        for item, color in (
            (pt_items[pair["pt_index"]], (40, 40, 230)),
            (onnx_items[pair["onnx_index"]], (230, 210, 30)),
        ):
            mask = item.get("mask")
            if mask is not None:
                resized = cv2.resize(mask.astype(np.float32), (width, height), interpolation=cv2.INTER_NEAREST) > 0.5
                overlay[resized] = color
            x1, y1, x2, y2 = (int(round(value)) for value in item["box"])
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
    rendered = cv2.addWeighted(image, 0.55, overlay, 0.45, 0)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), rendered):
        raise ValueError(f"unable to write gate comparison image: {output}")


def run(manifest_path: Path) -> int:
    from ultralytics import YOLO
    import torch
    import ultralytics

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pt_path = Path(manifest["pt_path"]).resolve()
    data_yaml = Path(manifest["data_yaml_path"]).resolve()
    output = manifest_path.parent / "result.json"
    pt_model = YOLO(str(pt_path))
    onnx_path = _export_onnx_isolated(pt_path, manifest_path.parent, manifest["image_size"])
    onnx_model = YOLO(str(onnx_path), task=manifest["task_type"])
    sample_reports = []
    for sample_index, source in enumerate(_samples(data_yaml), start=1):
        pt_result = pt_model.predict(source=source, imgsz=manifest["image_size"], conf=0.25, max_det=100, device=manifest["device"], verbose=False)[0]
        onnx_result = onnx_model.predict(source=source, imgsz=manifest["image_size"], conf=0.25, max_det=100, device="cpu", verbose=False)[0]
        pt_items = _normalize(pt_result)
        onnx_items = _normalize(onnx_result)
        sample_report = {"source": source, **_compare(pt_items, onnx_items, manifest["task_type"])}
        if manifest["task_type"] == "segment" and (
            not sample_report["passed"] or not sample_report["mask_consistency"]
        ):
            comparison_path = manifest_path.parent / f"comparison-{sample_index}.jpg"
            _write_comparison_overlay(Path(source), pt_items, onnx_items, sample_report["pairs"], comparison_path)
            sample_report["comparison_path"] = str(comparison_path.resolve())
        sample_reports.append(sample_report)
    consistency_passed = bool(sample_reports) and all(report["passed"] for report in sample_reports)
    mask_consistency_passed = bool(sample_reports) and all(report["mask_consistency"] for report in sample_reports)
    result = {
        "passed": consistency_passed,
        "gates": {
            "training": True,
            "pt": True,
            "onnx": onnx_path.is_file(),
            "consistency": consistency_passed,
            "mask_consistency": mask_consistency_passed,
        },
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
