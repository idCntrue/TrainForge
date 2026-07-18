import json
from pathlib import Path


class CorruptJsonLinesError(ValueError):
    pass


def read_json_lines(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    events: list[dict] = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) - 1:
                break
            raise CorruptJsonLinesError(f"invalid JSONL at line {index + 1}") from exc
        if not isinstance(value, dict):
            raise CorruptJsonLinesError(f"event at line {index + 1} must be an object")
        events.append(value)
    return events
