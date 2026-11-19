from __future__ import annotations

import numpy as np

from yolo_factory.labeling.mapping import build_class_mapping
from yolo_factory.labeling.predictions import extract_detections


class FakeTensor:
    def __init__(self, value) -> None:
        self._value = np.asarray(value)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self._value


class FakeBoxes:
    def __init__(self, xyxy, confidence, classes) -> None:
        self.xyxy = FakeTensor(xyxy)
        self.conf = FakeTensor(confidence)
        self.cls = FakeTensor(classes)

    def __len__(self) -> int:
        return len(self.xyxy._value)


class FakeMasks:
    def __init__(self, polygons) -> None:
        self.xyn = polygons

    def __len__(self) -> int:
        return len(self.xyn)

    def __getitem__(self, index):
        return self.xyn[index]


class FakeResult:
    def __init__(self, *, boxes=None, masks=None, names=None, shape=(100, 200)) -> None:
        self.boxes = boxes
        self.masks = masks
        self.names = names or {0: "red"}
        self.orig_shape = shape


def test_extracts_normalized_detection_boxes() -> None:
    result = FakeResult(
        boxes=FakeBoxes(
            xyxy=[[20, 10, 120, 60]],
            confidence=[0.8],
            classes=[0],
        ),
        shape=(100, 200),
    )

    detections = extract_detections(result, "detect")

    assert detections == [{
        "class_id": 0,
        "class_name": "red",
        "confidence": 0.8,
        "shape_type": "box",
        "coordinates": [0.35, 0.35, 0.5, 0.5],
    }]


def test_extracts_segment_polygons_and_skips_empty_masks() -> None:
    result = FakeResult(
        boxes=FakeBoxes(
            xyxy=[[0, 0, 10, 10], [0, 0, 10, 10]],
            confidence=[0.9, 0.7],
            classes=[0, 1],
        ),
        masks=FakeMasks([
            np.array([[0.1, 0.1], [0.5, 0.1], [0.5, 0.5]]),
            np.array([[0.2, 0.2]]),
        ]),
        names={0: "red", 1: "blue"},
    )

    detections = extract_detections(result, "segment")

    assert len(detections) == 1
    assert detections[0]["shape_type"] == "polygon"
    assert detections[0]["coordinates"] == [0.1, 0.1, 0.5, 0.1, 0.5, 0.5]


def test_class_mapping_uses_aliases_and_reports_unmapped_names() -> None:
    mapping = build_class_mapping({0: "entry-light", 1: "person"}, ["指示灯"], {"entry-light": "指示灯"})

    mapped = mapping.map_detection({
        "class_id": 0,
        "class_name": "entry-light",
        "confidence": 0.5,
        "shape_type": "box",
        "coordinates": [0.5, 0.5, 0.2, 0.2],
    })
    dropped = mapping.map_detection({
        "class_id": 1,
        "class_name": "person",
        "confidence": 0.5,
        "shape_type": "box",
        "coordinates": [0.5, 0.5, 0.2, 0.2],
    })

    assert mapped is not None
    assert mapped["class_id"] == 0
    assert mapped["class_name"] == "指示灯"
    assert dropped is None
    assert mapping.unmapped == ("person",)
