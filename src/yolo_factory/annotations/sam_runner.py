import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from yolo_factory.annotations.geometry import GeometryError, validate_polygon


def _clean_points(points: np.ndarray) -> list[tuple[int, int]]:
    cleaned: list[tuple[int, int]] = []
    for x, y in points:
        point = (int(x), int(y))
        if not cleaned or cleaned[-1] != point:
            cleaned.append(point)
    if len(cleaned) > 1 and cleaned[0] == cleaned[-1]:
        cleaned.pop()
    return cleaned


def mask_to_polygon(mask: np.ndarray, simplify: float = 0.2) -> list[float]:
    binary = (mask > 0).astype(np.uint8)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("SAM produced no mask contour")
    contour = max(contours, key=cv2.contourArea)
    epsilon_ratio = 0.001 + 0.019 * min(1.0, max(0.0, simplify))
    height, width = binary.shape[:2]
    base_epsilon = max(1.0, epsilon_ratio * cv2.arcLength(contour, True))
    last_error: Exception | None = None
    for epsilon in (base_epsilon, base_epsilon * 0.25):
        approximation = cv2.approxPolyDP(contour, epsilon, True).reshape(-1, 2)
        points = _clean_points(approximation)
        if len(points) < 3:
            last_error = ValueError("SAM mask contour is too small")
            continue
        polygon = [coordinate for x, y in points for coordinate in (float(x) / width, float(y) / height)]
        try:
            return validate_polygon(polygon)
        except GeometryError as exc:
            last_error = exc
    raise ValueError(f"SAM produced invalid mask contour: {last_error}") from last_error


def predict_with_model(model, manifest: dict) -> dict:
    image = cv2.imread(manifest["image_path"])
    if image is None:
        raise ValueError("SAM image cannot be decoded")
    height, width = image.shape[:2]
    positive = manifest.get("positive_points", [manifest.get("point")])
    positive = [point for point in positive if point is not None]
    negative = manifest.get("negative_points", [])
    pixel_points = [[point[0] * width, point[1] * height] for point in positive + negative]
    labels = [1] * len(positive) + [0] * len(negative)
    results = model.predict(manifest["image_path"], points=pixel_points, labels=labels, verbose=False)
    if not results or results[0].masks is None or len(results[0].masks.data) == 0:
        raise ValueError("SAM produced no mask")
    mask = results[0].masks.data[0].detach().cpu().numpy()
    polygon = mask_to_polygon(mask, manifest.get("simplify", 0.2))
    return {"polygon": polygon, "model": manifest["model"]}


def run(manifest_path: Path) -> int:
    from ultralytics import SAM

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = predict_with_model(SAM(manifest["model"]), manifest)
    (manifest_path.parent / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    return run(parser.parse_args().manifest)


if __name__ == "__main__":
    raise SystemExit(main())
