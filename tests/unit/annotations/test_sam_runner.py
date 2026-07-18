import cv2
import numpy as np

from yolo_factory.annotations.geometry import validate_polygon
from yolo_factory.annotations.sam_runner import mask_to_polygon


def test_mask_polygon_removes_adjacent_and_closing_duplicates(monkeypatch) -> None:
    approximation = np.asarray([[[0, 0]], [[9, 0]], [[9, 0]], [[9, 9]], [[0, 9]], [[0, 0]]], dtype=np.int32)
    monkeypatch.setattr(cv2, "approxPolyDP", lambda *args, **kwargs: approximation)

    polygon = mask_to_polygon(np.ones((10, 10), dtype=np.uint8))

    assert polygon == [0.0, 0.0, 0.9, 0.0, 0.9, 0.9, 0.0, 0.9]
    assert validate_polygon(polygon) == polygon


def test_mask_polygon_retries_when_initial_simplification_degenerates(monkeypatch) -> None:
    calls: list[float] = []

    def approximate(contour, epsilon, closed):
        del contour, closed
        calls.append(epsilon)
        if len(calls) == 1:
            return np.asarray([[[0, 0]], [[9, 0]]], dtype=np.int32)
        return np.asarray([[[0, 0]], [[9, 0]], [[9, 9]], [[0, 9]]], dtype=np.int32)

    monkeypatch.setattr(cv2, "approxPolyDP", approximate)

    polygon = mask_to_polygon(np.ones((10, 10), dtype=np.uint8), simplify=1.0)

    assert len(calls) == 2
    assert calls[1] < calls[0]
    assert validate_polygon(polygon) == polygon
