import json
from dataclasses import dataclass
from pathlib import Path


class CorruptJsonLinesError(ValueError):
    pass


@dataclass(frozen=True)
class JsonLinesBatch:
    events: list[dict]
    offset: int
    identity: str


def read_json_lines_since(
    path: Path,
    *,
    offset: int = 0,
    identity: str | None = None,
) -> JsonLinesBatch:
    if not path.is_file():
        return JsonLinesBatch([], 0, "")
    stat = path.stat()
    current_identity = f"{stat.st_dev}:{stat.st_ino}"
    if identity != current_identity or offset < 0 or offset > stat.st_size:
        offset = 0

    events: list[dict] = []
    next_offset = offset
    with path.open("rb") as stream:
        stream.seek(offset)
        while True:
            line_start = stream.tell()
            line = stream.readline()
            if not line:
                break
            if not line.endswith(b"\n"):
                next_offset = line_start
                break
            next_offset = stream.tell()
            if not line.strip():
                continue
            try:
                value = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise CorruptJsonLinesError(f"invalid JSONL at byte {line_start}") from exc
            if not isinstance(value, dict):
                raise CorruptJsonLinesError(f"event at byte {line_start} must be an object")
            events.append(value)
    return JsonLinesBatch(events, next_offset, current_identity)


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
