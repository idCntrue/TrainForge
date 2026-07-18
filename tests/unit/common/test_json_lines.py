from pathlib import Path

import pytest

from yolo_factory.common.json_lines import CorruptJsonLinesError, read_json_lines


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
