import json


def encode_task_classes(classes: list[str], display_names: dict[str, str] | None = None) -> str:
    return json.dumps(
        {"classes": classes, "display_names": display_names or {}},
        ensure_ascii=False,
    )


def decode_task_classes(value: str) -> tuple[list[str], dict[str, str]]:
    payload = json.loads(value)
    if isinstance(payload, list):
        return list(payload), {}
    return list(payload.get("classes", [])), dict(payload.get("display_names", {}))
