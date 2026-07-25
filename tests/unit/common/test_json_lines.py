from pathlib import Path

import pytest

from yolo_factory.common.json_lines import CorruptJsonLinesError, read_json_lines, read_json_lines_since


def test_read_json_lines_ignores_incomplete_final_line(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_text('{"status":"running"}\n{"status":', encoding="utf-8")

    assert read_json_lines(path) == [{"status": "running"}]


def test_read_json_lines_rejects_corrupt_middle_line(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_text(
        '{"status":"running"}\nnot-json\n{"status":"completed"}\n',
        encoding="utf-8",
    )

    with pytest.raises(CorruptJsonLinesError, match="line 2"):
        read_json_lines(path)


def test_read_json_lines_requires_object_events(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_text('["running"]\n', encoding="utf-8")

    with pytest.raises(CorruptJsonLinesError, match="line 1 must be an object"):
        read_json_lines(path)


def test_read_json_lines_since_only_returns_appended_events(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_text('{"epoch": 1}\n', encoding="utf-8")

    first = read_json_lines_since(path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write('{"epoch": 2}\n')
    second = read_json_lines_since(path, offset=first.offset, identity=first.identity)

    assert first.events == [{"epoch": 1}]
    assert second.events == [{"epoch": 2}]
    assert second.offset > first.offset
    assert second.identity == first.identity


def test_read_json_lines_since_does_not_advance_past_incomplete_final_event(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_bytes(b'{"epoch": 1}\n{"epoch":')

    first = read_json_lines_since(path)
    with path.open("ab") as stream:
        stream.write(b' 2}\n')
    second = read_json_lines_since(path, offset=first.offset, identity=first.identity)

    assert first.events == [{"epoch": 1}]
    assert second.events == [{"epoch": 2}]


def test_read_json_lines_since_restarts_after_file_is_replaced(tmp_path: Path) -> None:
    path = tmp_path / "progress.jsonl"
    path.write_text('{"epoch": 1}\n{"epoch": 2}\n', encoding="utf-8")
    first = read_json_lines_since(path)
    path.unlink()
    path.write_text('{"epoch": 3}\n', encoding="utf-8")

    replaced = read_json_lines_since(path, offset=first.offset, identity=first.identity)

    assert replaced.events == [{"epoch": 3}]
    assert replaced.offset == path.stat().st_size
