from pathlib import Path

import onnx
from onnx import TensorProto, helper

from yolo_factory.models.imported_inspector import inspect_imported_model


def _write_onnx(
    path: Path,
    *,
    metadata: dict[str, str] | None = None,
    segment_outputs: bool = False,
) -> None:
    input_info = helper.make_tensor_value_info("images", TensorProto.FLOAT, [1, 3, 640, 640])
    output_infos = [helper.make_tensor_value_info("output0", TensorProto.FLOAT, [1, 300, 38])]
    if segment_outputs:
        output_infos.append(helper.make_tensor_value_info("output1", TensorProto.FLOAT, [1, 32, 160, 160]))
    graph = helper.make_graph([], "imported-model", [input_info], output_infos)
    model = helper.make_model(graph)
    for key, value in (metadata or {}).items():
        entry = model.metadata_props.add()
        entry.key = key
        entry.value = value
    onnx.save(model, path)


def test_reads_segment_task_and_class_names_from_onnx_metadata(tmp_path: Path) -> None:
    path = tmp_path / "best.onnx"
    _write_onnx(
        path,
        metadata={"task": "segment", "names": "{0: 'door', 1: 'button'}"},
        segment_outputs=True,
    )

    inspected = inspect_imported_model(path, "onnx", "segment")

    assert inspected == {
        "task_type": "segment",
        "class_names": ["door", "button"],
        "format": "onnx",
    }


def test_infers_segment_from_mask_prototype_output_without_metadata(tmp_path: Path) -> None:
    path = tmp_path / "best.onnx"
    _write_onnx(path, segment_outputs=True)

    inspected = inspect_imported_model(path, "onnx", "segment")

    assert inspected["task_type"] == "segment"


def test_does_not_accept_detect_onnx_as_segment(tmp_path: Path) -> None:
    path = tmp_path / "best.onnx"
    _write_onnx(path, metadata={"task": "detect", "names": "['item']"})

    inspected = inspect_imported_model(path, "onnx", "segment")

    assert inspected["task_type"] == "detect"


def test_infers_detect_from_single_output_without_metadata(tmp_path: Path) -> None:
    path = tmp_path / "best.onnx"
    _write_onnx(path)

    inspected = inspect_imported_model(path, "onnx", "segment")

    assert inspected["task_type"] == "detect"
