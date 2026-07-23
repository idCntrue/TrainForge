import ast
from pathlib import Path


def _class_names(value: object) -> list[str]:
    if isinstance(value, str):
        try:
            value = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            return []
    if isinstance(value, dict):
        return [str(value[index]) for index in sorted(value)]
    if isinstance(value, (list, tuple)):
        return [str(name) for name in value]
    return []


def _inspect_onnx(path: Path, artifact_format: str) -> dict:
    import onnx

    model = onnx.load(str(path), load_external_data=False)
    metadata = {entry.key: entry.value for entry in model.metadata_props}
    task_type = metadata.get("task", "").strip().lower()
    if not task_type:
        output_shapes = [
            [dimension.dim_value for dimension in output.type.tensor_type.shape.dim]
            for output in model.graph.output
        ]
        has_mask_prototypes = any(
            len(shape) == 4 and shape[1] == 32 and shape[2] > 0 and shape[3] > 0
            for shape in output_shapes
        )
        task_type = "segment" if has_mask_prototypes else "detect"
    return {
        "task_type": task_type,
        "class_names": _class_names(metadata.get("names")),
        "format": artifact_format,
    }


def inspect_imported_model(path: Path, artifact_format: str, expected_task: str) -> dict:
    if artifact_format.lower() == "onnx":
        return _inspect_onnx(path, artifact_format)

    from ultralytics import YOLO

    model = YOLO(str(path), task=expected_task)
    return {
        "task_type": str(model.task or ""),
        "class_names": _class_names(model.names),
        "format": artifact_format,
    }
