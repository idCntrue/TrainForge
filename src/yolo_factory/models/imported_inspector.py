from pathlib import Path


def inspect_imported_model(path: Path, artifact_format: str) -> dict:
    from ultralytics import YOLO

    model = YOLO(str(path))
    names = model.names
    if isinstance(names, dict):
        class_names = [str(names[index]) for index in sorted(names)]
    elif isinstance(names, (list, tuple)):
        class_names = [str(name) for name in names]
    else:
        class_names = []
    return {
        "task_type": str(model.task or ""),
        "class_names": class_names,
        "format": artifact_format,
    }
