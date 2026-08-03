from pathlib import Path

import numpy as np
import pytest

from yolo_factory.inference.runner import (
    ONNX_RAW_PREVIEW_LIMIT,
    _detections,
    _capture_onnx_output,
    _raw_onnx_diagnostic,
    _onnx_tensor_summary,
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


def test_onnx_tensor_summary_is_bounded_and_reports_finite_range() -> None:
    summary = _onnx_tensor_summary(
        "output0",
        np.asarray([[1.0, np.nan, np.inf], [-2.5, 7.0, 8.0]], dtype=np.float32),
    )

    assert summary == {
        "name": "output0",
        "shape": [2, 3],
        "dtype": "float32",
        "elements": 6,
        "min": -2.5,
        "max": 8.0,
        "preview": [1.0, None, None, -2.5, 7.0, 8.0],
    }


def test_onnx_tensor_summary_limits_preview_values() -> None:
    summary = _onnx_tensor_summary("output1", np.arange(ONNX_RAW_PREVIEW_LIMIT + 1, dtype=np.float32))

    assert len(summary["preview"]) == ONNX_RAW_PREVIEW_LIMIT
    assert summary["preview"][-1] == float(ONNX_RAW_PREVIEW_LIMIT - 1)


def test_capture_onnx_output_records_model_io_and_bounded_outputs() -> None:
    class Session:
        def get_inputs(self):
            return [type("Node", (), {"name": "images"})()]

        def get_outputs(self):
            return [type("Node", (), {"name": "output0"})()]

        def run(self, output_names, feed):
            assert output_names is None
            assert list(feed) == ["images"]
            return [np.asarray([[0.1, 0.9]], dtype=np.float32)]

    predictor = type("Predictor", (), {
        "model": type("Backend", (), {"session": Session()})(),
        "im": FakeTensor(np.zeros((1, 3, 640, 640), dtype=np.float32)),
    })()

    snapshot = _capture_onnx_output(predictor)

    assert snapshot["input"] == {"name": "images", "shape": [1, 3, 640, 640], "dtype": "float32"}
    assert snapshot["outputs"][0] == {
        "name": "output0", "shape": [1, 2], "dtype": "float32", "elements": 2,
        "min": pytest.approx(0.1), "max": pytest.approx(0.9), "preview": pytest.approx([0.1, 0.9]),
    }
    assert snapshot["preview_limit"] == ONNX_RAW_PREVIEW_LIMIT


def test_capture_onnx_output_raises_clear_error_when_session_is_unavailable() -> None:
    predictor = type("Predictor", (), {"model": object(), "im": FakeTensor([1])})()

    try:
        _capture_onnx_output(predictor)
    except RuntimeError as error:
        assert str(error) == "ONNX Runtime session is unavailable"
    else:
        raise AssertionError("Expected unavailable ONNX session to raise")


def test_capture_onnx_output_supports_current_ultralytics_backend_wrapper() -> None:
    class Session:
        def get_inputs(self):
            return [type("Node", (), {"name": "images"})()]

        def get_outputs(self):
            return [type("Node", (), {"name": "output0"})()]

        def run(self, output_names, feed):
            return [np.asarray([1.0], dtype=np.float32)]

    predictor = type("Predictor", (), {
        "model": type("AutoBackend", (), {"backend": type("ONNXBackend", (), {"session": Session()})()})(),
        "im": FakeTensor(np.zeros((1, 3, 32, 32), dtype=np.float32)),
    })()

    assert _capture_onnx_output(predictor)["outputs"][0]["preview"] == [1.0]


def test_capture_onnx_output_rebuilds_preprocessed_input_when_predictor_does_not_retain_it() -> None:
    class Session:
        def get_inputs(self):
            return [type("Node", (), {"name": "images"})()]

        def get_outputs(self):
            return [type("Node", (), {"name": "output0"})()]

        def run(self, output_names, feed):
            assert feed["images"].shape == (1, 3, 32, 32)
            return [np.asarray([1.0], dtype=np.float32)]

    predictor = type("Predictor", (), {
        "model": type("AutoBackend", (), {"backend": type("ONNXBackend", (), {"session": Session()})()})(),
        "im": None,
        "batch": (['input.jpg'], [np.zeros((32, 32, 3), dtype=np.uint8)], ['image 1/1']),
        "preprocess": lambda self, images: FakeTensor(np.zeros((1, 3, 32, 32), dtype=np.float32)),
    })()

    assert _capture_onnx_output(predictor)["input"]["shape"] == [1, 3, 32, 32]


def test_raw_onnx_diagnostic_preserves_success_when_capture_fails() -> None:
    diagnostic = _raw_onnx_diagnostic("onnx", type("Predictor", (), {"model": object(), "im": FakeTensor([1])})())

    assert diagnostic == {"raw_onnx_output_error": "ONNX Runtime session is unavailable"}


def test_raw_onnx_diagnostic_explains_pt_runtime_has_no_onnx_output() -> None:
    assert _raw_onnx_diagnostic("pt", None) == {
        "raw_onnx_output_error": "原始 ONNX 输出仅适用于 ONNX Runtime 推理",
    }


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
