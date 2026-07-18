from __future__ import annotations

import re
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class PathConversion:
    value: str
    status: Literal["converted", "external", "unchanged"]


@dataclass(frozen=True)
class JsonPathConversion:
    value: Any
    converted: int
    external_paths: tuple[str, ...]


@dataclass(frozen=True)
class DatabaseMigrationReport:
    applied: bool
    updated_values: int
    external_paths: tuple[str, ...]
    missing_paths: tuple[str, ...]
    backup_path: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "updated_values": self.updated_values,
            "external_paths": list(self.external_paths),
            "missing_paths": list(self.missing_paths),
            "backup_path": self.backup_path,
        }


_PATH_COLUMNS = (
    ("video_assets", "stored_path", False),
    ("frame_batches", "manifest_path", False),
    ("frame_assets", "stored_path", False),
    ("annotation_images", "image_path", False),
    ("annotation_exports", "zip_path", False),
    ("dataset_releases", "release_path", False),
    ("training_runs", "base_model", False),
    ("training_runs", "config_json", True),
    ("training_runs", "run_directory", False),
    ("model_versions", "config_json", True),
    ("model_versions", "gate_report_path", False),
    ("inference_runs", "config_json", True),
    ("inference_runs", "output_directory", False),
    ("inference_runs", "result_path", False),
)


def _portable(value: str) -> str:
    return value.replace("\\", "/").rstrip("/")


def _is_absolute(value: str) -> bool:
    return value.startswith("/") or re.match(r"^[A-Za-z]:/", value) is not None


def convert_storage_path(value: str, old_root: str, new_root: Path) -> PathConversion:
    portable_value = _portable(value)
    portable_old = _portable(old_root)
    portable_new = _portable(new_root.as_posix())
    folded_value = portable_value.casefold()
    folded_old = portable_old.casefold()

    if folded_value == folded_old or folded_value.startswith(f"{folded_old}/"):
        suffix = portable_value[len(portable_old):].lstrip("/")
        converted = portable_new if not suffix else f"{portable_new}/{suffix}"
        return PathConversion(converted, "converted")

    if folded_value == portable_new.casefold() or folded_value.startswith(f"{portable_new.casefold()}/"):
        return PathConversion(value, "unchanged")
    if _is_absolute(portable_value):
        return PathConversion(value, "external")
    return PathConversion(value, "unchanged")


def convert_json_paths(value: Any, old_root: str, new_root: Path) -> JsonPathConversion:
    if isinstance(value, str):
        result = convert_storage_path(value, old_root, new_root)
        return JsonPathConversion(
            result.value,
            1 if result.status == "converted" else 0,
            (value,) if result.status == "external" else (),
        )
    if isinstance(value, list):
        converted_items = [convert_json_paths(item, old_root, new_root) for item in value]
        return JsonPathConversion(
            [item.value for item in converted_items],
            sum(item.converted for item in converted_items),
            tuple(path for item in converted_items for path in item.external_paths),
        )
    if isinstance(value, dict):
        converted_items = {
            key: convert_json_paths(item, old_root, new_root)
            for key, item in value.items()
        }
        return JsonPathConversion(
            {key: item.value for key, item in converted_items.items()},
            sum(item.converted for item in converted_items.values()),
            tuple(path for item in converted_items.values() for path in item.external_paths),
        )
    return JsonPathConversion(value, 0, ())


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}


def _converted_targets(value: Any, old_root: str, new_root: Path) -> list[str]:
    if isinstance(value, str):
        result = convert_storage_path(value, old_root, new_root)
        return [result.value] if result.status == "converted" else []
    if isinstance(value, list):
        return [path for item in value for path in _converted_targets(item, old_root, new_root)]
    if isinstance(value, dict):
        return [path for item in value.values() for path in _converted_targets(item, old_root, new_root)]
    return []


def _backup_database(connection: sqlite3.Connection, database: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = database.with_name(f"{database.stem}.backup-{stamp}{database.suffix}")
    destination = sqlite3.connect(backup)
    try:
        connection.backup(destination)
    finally:
        destination.close()
    return backup


def migrate_storage_paths(
    database: Path,
    old_root: str,
    new_root: Path,
    *,
    apply: bool = False,
) -> DatabaseMigrationReport:
    if not database.is_file():
        raise FileNotFoundError(database)
    resolved_new_root = new_root.resolve()
    connection = sqlite3.connect(database)
    pending: list[tuple[str, str, int, str]] = []
    converted_targets: list[str] = []
    external_paths: list[str] = []
    updated_values = 0
    backup_path: Path | None = None
    try:
        tables = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        for table, column, is_json in _PATH_COLUMNS:
            if table not in tables or column not in _table_columns(connection, table):
                continue
            rows = connection.execute(
                f'SELECT rowid, "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL'
            )
            for rowid, raw_value in rows:
                value = str(raw_value)
                if is_json:
                    try:
                        decoded = json.loads(value)
                    except json.JSONDecodeError as exc:
                        raise ValueError(f"invalid JSON in {table}.{column} rowid={rowid}") from exc
                    result = convert_json_paths(decoded, old_root, resolved_new_root)
                    converted_targets.extend(_converted_targets(decoded, old_root, resolved_new_root))
                    external_paths.extend(result.external_paths)
                    if result.converted:
                        pending.append((table, column, int(rowid), json.dumps(result.value, ensure_ascii=False, sort_keys=True)))
                        updated_values += result.converted
                else:
                    result = convert_storage_path(value, old_root, resolved_new_root)
                    if result.status == "converted":
                        pending.append((table, column, int(rowid), result.value))
                        converted_targets.append(result.value)
                        updated_values += 1
                    elif result.status == "external":
                        external_paths.append(value)

        missing_paths = tuple(sorted({path for path in converted_targets if not Path(path).exists()}))
        if apply:
            backup_path = _backup_database(connection, database)
            try:
                connection.execute("BEGIN IMMEDIATE")
                for table, column, rowid, value in pending:
                    connection.execute(
                        f'UPDATE "{table}" SET "{column}" = ? WHERE rowid = ?',
                        (value, rowid),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return DatabaseMigrationReport(
            applied=apply,
            updated_values=updated_values,
            external_paths=tuple(sorted(set(external_paths))),
            missing_paths=missing_paths,
            backup_path=str(backup_path) if backup_path else None,
        )
    finally:
        connection.close()
