from __future__ import annotations


def _clip(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


def _normalized_box(xyxy, width: int, height: int) -> list[float] | None:
    x1, y1, x2, y2 = (float(value) for value in xyxy)
    x1, x2 = sorted((_clip(x1 / width), _clip(x2 / width)))
    y1, y2 = sorted((_clip(y1 / height), _clip(y2 / height)))
    box_width = x2 - x1
    box_height = y2 - y1
    if box_width <= 0 or box_height <= 0:
        return None
    return [(x1 + x2) / 2, (y1 + y2) / 2, box_width, box_height]


def _normalized_polygon(points) -> list[float] | None:
    coordinates: list[float] = []
    for point in points:
        coordinates.extend([_clip(point[0]), _clip(point[1])])
    if len(coordinates) < 6:
        return None
    return coordinates


def extract_detections(result, task_type: str) -> list[dict]:
    boxes = getattr(result, "boxes", None)
    if boxes is None or len(boxes) == 0:
        return []
    xyxy = boxes.xyxy.detach().cpu().numpy()
    confidence = boxes.conf.detach().cpu().numpy()
    classes = boxes.cls.detach().cpu().numpy()
    names = result.names
    masks = result.masks.xyn if getattr(result, "masks", None) is not None else None
    image_height, image_width = result.orig_shape[:2]
    detections: list[dict] = []
    for index in range(len(xyxy)):
        class_id = int(classes[index])
        score = float(confidence[index])
        if task_type == "segment":
            polygon = _normalized_polygon(masks[index]) if masks is not None and index < len(masks) else None
            if polygon is None:
                continue
            detections.append({
                "class_id": class_id,
                "class_name": str(names[class_id]),
                "confidence": score,
                "shape_type": "polygon",
                "coordinates": polygon,
            })
            continue
        box = _normalized_box(xyxy[index], image_width, image_height)
        if box is None:
            continue
        detections.append({
            "class_id": class_id,
            "class_name": str(names[class_id]),
            "confidence": score,
            "shape_type": "box",
            "coordinates": box,
        })
    return detections
