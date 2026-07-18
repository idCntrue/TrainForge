import hashlib
from pathlib import Path


def file_metadata(path: Path) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "size_bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def box_iou(left: list[float], right: list[float]) -> float:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    intersection = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def compare_predictions(
    pt: list[dict],
    onnx: list[dict],
    *,
    box_iou_threshold: float = 0.8,
    confidence_delta: float = 0.15,
) -> dict:
    unmatched = list(range(len(onnx)))
    matched = 0
    differences: list[dict] = []
    for pt_item in pt:
        candidates = [index for index in unmatched if onnx[index]["class_id"] == pt_item["class_id"]]
        if not candidates:
            differences.append({"reason": "class_missing", "pt": pt_item})
            continue
        best_index = max(candidates, key=lambda index: box_iou(pt_item["box"], onnx[index]["box"]))
        onnx_item = onnx[best_index]
        iou = box_iou(pt_item["box"], onnx_item["box"])
        delta = abs(pt_item["confidence"] - onnx_item["confidence"])
        if iou >= box_iou_threshold and delta <= confidence_delta:
            matched += 1
            unmatched.remove(best_index)
        else:
            differences.append({"reason": "value_mismatch", "box_iou": iou, "confidence_delta": delta})
    passed = matched == len(pt) == len(onnx)
    return {"passed": passed, "matched": matched, "pt_count": len(pt), "onnx_count": len(onnx), "differences": differences}
