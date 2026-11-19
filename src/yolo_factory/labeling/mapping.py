from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassMapping:
    """Model class id -> task class id, by exact (or aliased) class name."""

    class_ids: dict[int, int]
    names: dict[int, str]
    unmapped: tuple[str, ...]

    def map_detection(self, detection: dict) -> dict | None:
        model_id = int(detection.get("class_id", -1))
        task_id = self.class_ids.get(model_id)
        if task_id is None:
            return None
        item = {
            "class_id": task_id,
            "class_name": self.names[task_id],
            "shape_type": detection["shape_type"],
            "coordinates": detection["coordinates"],
        }
        if detection.get("confidence") is not None:
            item["confidence"] = float(detection["confidence"])
        return item


def build_class_mapping(
    model_class_names: dict[int, str] | list[str],
    task_classes: list[str],
    aliases: dict[str, str] | None = None,
) -> ClassMapping:
    if isinstance(model_class_names, dict):
        model_classes = {int(key): str(value) for key, value in model_class_names.items()}
    else:
        model_classes = {index: name for index, name in enumerate(model_class_names)}
    task_lookup = {name: index for index, name in enumerate(task_classes)}
    alias_lookup = aliases or {}
    class_ids: dict[int, int] = {}
    names: dict[int, str] = {}
    unmapped: list[str] = []
    for model_id, model_name in sorted(model_classes.items()):
        target = alias_lookup.get(model_name, model_name)
        task_id = task_lookup.get(target)
        if task_id is None:
            unmapped.append(model_name)
            continue
        class_ids[model_id] = task_id
        names[task_id] = task_classes[task_id]
    return ClassMapping(class_ids=class_ids, names=names, unmapped=tuple(sorted(set(unmapped))))
