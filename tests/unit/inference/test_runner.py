from pathlib import Path

import numpy as np

from yolo_factory.inference.runner import (
    _detections,
    ensure_browser_compatible_video,
    media_for_source,
    prediction_inputs,
    prediction_source,
)


class FakeTensor:
    def __init__(self, value) -> None:
        self.value = np.asarray(value)

    def detach(self):
        return self

    def cpu(self):
        return self

    def numpy(self):
        return self.value


def test_detections_include_normalized_segmentation_polygon() -> None:
    result = type("Result", (), {
        "boxes": type("Boxes", (), {
            "xyxy": FakeTensor([[10, 20, 30, 40]]),
            "conf": FakeTensor([0.85]),
            "cls": FakeTensor([1]),
        })(),
        "masks": type("Masks", (), {
            "xyn": [np.asarray([[0.1, 0.2], [0.3, 0.2], [0.3, 0.4]])],
        })(),
        "names": {1: "defect"},
    })()

    assert _detections(result) == [{
        "class_id": 1,
        "class_name": "defect",
        "confidence": 0.85,
        "box": [10.0, 20.0, 30.0, 40.0],
        "polygon": [0.1, 0.2, 0.3, 0.2, 0.3, 0.4],
    }]


def test_detection_model_omits_polygon() -> None:
    result = type("Result", (), {
        "boxes": type("Boxes", (), {
            "xyxy": FakeTensor([[1, 2, 3, 4]]),
            "conf": FakeTensor([0.5]),
            "cls": FakeTensor([0]),
        })(),
        "masks": None,
        "names": {0: "object"},
    })()

    assert "polygon" not in _detections(result)[0]


def test_video_and_image_use_scalar_source_while_batch_keeps_list() -> None:
    assert prediction_source({"mode": "video", "sources": ["input.mp4"]}) == "input.mp4"
    assert prediction_source({"mode": "image", "sources": ["input.jpg"]}) == "input.jpg"
    assert prediction_source({"mode": "batch", "sources": ["a.jpg", "b.jpg"]}) == ["a.jpg", "b.jpg"]


def test_onnx_batch_is_split_into_single_image_prediction_inputs() -> None:
    manifest = {"mode": "batch", "runtime": "onnx", "sources": ["a.jpg", "b.jpg"]}

    assert prediction_inputs(manifest) == ["a.jpg", "b.jpg"]


def test_pt_batch_remains_one_batched_prediction_input() -> None:
    manifest = {"mode": "batch", "runtime": "pt", "sources": ["a.jpg", "b.jpg"]}

    assert prediction_inputs(manifest) == [["a.jpg", "b.jpg"]]


def test_batch_media_is_matched_by_source_stem_not_filesystem_order() -> None:
    media = ["outputs/b.jpg", "outputs/a.jpg"]
    assert media_for_source("inputs/a.jpg", media) == "outputs/a.jpg"
    assert media_for_source("inputs/b.jpg", media) == "outputs/b.jpg"


def test_video_output_is_transcoded_to_browser_compatible_mp4(tmp_path: Path) -> None:
    avi = tmp_path / "annotated.avi"
    avi.write_bytes(b"avi")
    commands = []

    def transcode(command, **kwargs):
        commands.append((command, kwargs))
        Path(command[-1]).write_bytes(b"mp4")

    media = ensure_browser_compatible_video(
        [str(avi)],
        ffmpeg_executable="ffmpeg-test",
        run_command=transcode,
    )

    assert media == [str(tmp_path / "annotated.mp4")]
    assert commands[0][0] == [
        "ffmpeg-test", "-y", "-i", str(avi), "-an", "-c:v", "libx264",
        "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(tmp_path / "annotated.mp4"),
    ]
    assert commands[0][1] == {"check": True, "capture_output": True, "text": True}
    assert not avi.exists()
