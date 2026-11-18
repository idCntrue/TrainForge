"""Recompute per-class test metrics for completed runs with the current code.

Historical ``test-metrics.json`` files were produced before the per-class rows
were aligned with ultralytics' ``ap_class_index``. Overall metrics were always
correct, so a rerun must reproduce them exactly; any drift means the run is not
reproducible (different weights, dataset, or environment) and the new file must
not replace the old one.

Only generated reports are rewritten. Weights and datasets are read-only.
Existing reports are copied to ``<run>/.backfill-<timestamp>/`` before writing.

Usage:
    python scripts/backfill_test_metrics.py --runs-root D:/YOLO_DATA/training-runs
    python scripts/backfill_test_metrics.py --runs-root D:/YOLO_DATA/training-runs --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from yolo_factory.training.evaluation import normalize_test_metrics, write_test_metrics  # noqa: E402
from yolo_factory.training.quality_report import build_quality_report  # noqa: E402

OVERALL_TOLERANCE = 1e-6


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def class_names_from_yaml(path: Path) -> list[str]:
    import yaml

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names = payload.get("names", [])
    if isinstance(names, dict):
        return [names[index] for index in sorted(names)]
    return list(names)


def overall_delta(old: dict, new: dict) -> float:
    keys = ("precision", "recall", "map50", "map50_95", "map50_box", "map50_95_box", "map50_mask", "map50_95_mask")
    worst = 0.0
    for key in keys:
        before, after = old.get(key), new.get(key)
        if before is None and after is None:
            continue
        if before is None or after is None:
            return float("inf")
        worst = max(worst, abs(float(before) - float(after)))
    return worst


def row_changes(old_rows: list[dict], new_rows: list[dict]) -> list[str]:
    before = {row.get("class_id"): row for row in old_rows}
    after = {row.get("class_id"): row for row in new_rows}
    changes = []
    for class_id in sorted(set(before) | set(after)):
        old_row, new_row = before.get(class_id, {}), after.get(class_id, {})
        name = new_row.get("class_name") or old_row.get("class_name")
        for field in ("precision", "recall", "map50", "map50_95"):
            old_value, new_value = old_row.get(field), new_row.get(field)
            if old_value is None and new_value is None:
                continue
            if old_value is None or new_value is None or abs(float(old_value) - float(new_value)) > 1e-9:
                changes.append(f"{name}.{field}: {fmt(old_value)} -> {fmt(new_value)}")
                break
    return changes


def fmt(value) -> str:
    return "null" if value is None else f"{value:.4f}"


def backup_reports(run_dir: Path, stamp: str) -> Path:
    backup_dir = run_dir / f".backfill-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    for name in ("test-metrics.json", "quality-report.json"):
        source = run_dir / name
        if source.is_file():
            shutil.copy2(source, backup_dir / name)
    return backup_dir


def evaluate(run_dir: Path, spec: dict, device: str) -> dict:
    from ultralytics import YOLO

    data_yaml = run_dir / "dataset" / "data.yaml"
    weight = run_dir / "ultralytics" / "weights" / "best.pt"
    class_names = class_names_from_yaml(data_yaml)
    scratch = Path(tempfile.mkdtemp(prefix="backfill-val-"))
    try:
        model = YOLO(str(weight))
        result = model.val(
            data=str(data_yaml),
            split="test",
            batch=int(spec.get("batch", 4)),
            imgsz=int(spec.get("image_size", 640)),
            device=device,
            workers=0,
            project=str(scratch),
            name="val",
            plots=False,
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    return normalize_test_metrics(result, task_type=spec.get("task_type", "segment"), class_names=class_names)


def process_run(run_dir: Path, device: str, apply: bool, stamp: str) -> dict:
    metrics_path = run_dir / "test-metrics.json"
    manifest_path = run_dir / "manifest.json"
    data_yaml = run_dir / "dataset" / "data.yaml"
    weight_path = run_dir / "ultralytics" / "weights" / "best.pt"
    for required in (metrics_path, manifest_path, data_yaml, weight_path):
        if not required.is_file():
            return {"run": run_dir.name, "skipped": f"missing {required.name}"}

    manifest = load_json(manifest_path)
    spec = manifest.get("spec", {})
    old_report = load_json(metrics_path)
    started = time.monotonic()
    new_report = evaluate(run_dir, spec, device)
    elapsed = time.monotonic() - started

    delta = overall_delta(old_report.get("overall", {}), new_report.get("overall", {}))
    changes = row_changes(old_report.get("per_class", []), new_report.get("per_class", []))
    result = {
        "run": run_dir.name,
        "elapsed": round(elapsed, 1),
        "overall_delta": delta,
        "reproducible": delta <= OVERALL_TOLERANCE,
        "class_rows_changed": len(changes),
        "changes": changes,
    }

    quality_path = run_dir / "quality-report.json"
    old_quality = load_json(quality_path) if quality_path.is_file() else {}
    dataset_quality_path = run_dir / "dataset-quality.json"
    dataset_quality = load_json(dataset_quality_path) if dataset_quality_path.is_file() else {}
    new_quality = (
        build_quality_report(
            spec.get("task_type", "segment"),
            dataset_quality,
            new_report,
            old_quality.get("best_epoch"),
        )
        if dataset_quality
        else None
    )
    if new_quality is not None:
        old_verdict = old_quality.get("verdict")
        result["verdict"] = {"before": old_verdict, "after": new_quality["verdict"]}
        old_weakest = [row.get("class_name") for row in old_quality.get("weakest_classes", [])]
        new_weakest = [row.get("class_name") for row in new_quality.get("weakest_classes", [])]
        if old_weakest != new_weakest:
            result["weakest_classes"] = {"before": old_weakest, "after": new_weakest}

    if not result["reproducible"]:
        result["applied"] = False
        result["error"] = "overall metrics drifted; refusing to overwrite"
        return result

    if apply:
        result["backup_dir"] = str(backup_reports(run_dir, stamp))
        write_test_metrics(metrics_path, new_report)
        if new_quality is not None:
            temporary = quality_path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(new_quality, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")
            temporary.replace(quality_path)
        result["applied"] = True
    else:
        result["applied"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, default=Path("D:/YOLO_DATA/training-runs"))
    parser.add_argument("--run", action="append", default=[], help="restrict to these run directory names")
    parser.add_argument("--device", default=None, help="default: spec device, or cpu when CUDA is unavailable")
    parser.add_argument("--apply", action="store_true", help="write files (default is a dry run)")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    import torch

    device = args.device or ("cuda:0" if torch.cuda.is_available() else "cpu")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dirs = sorted(path for path in args.runs_root.iterdir() if path.is_dir())
    if args.run:
        wanted = set(args.run)
        run_dirs = [path for path in run_dirs if path.name in wanted]

    print(f"device={device} apply={args.apply} runs_root={args.runs_root}")
    results = []
    for run_dir in run_dirs:
        print(f"\n== {run_dir.name}")
        try:
            result = process_run(run_dir, device, args.apply, stamp)
        except Exception as error:  # noqa: BLE001 - one bad run must not stop the sweep
            result = {"run": run_dir.name, "error": f"{type(error).__name__}: {error}"}
        results.append(result)
        if result.get("skipped"):
            print(f"  skipped: {result['skipped']}")
            continue
        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            continue
        verdict = result.get("verdict")
        verdict_text = f" verdict {verdict['before']} -> {verdict['after']}" if verdict else ""
        print(
            f"  {result['elapsed']}s overall_drift={result['overall_delta']:.2e} "
            f"rows_changed={result['class_rows_changed']}{verdict_text} applied={result['applied']}"
        )
        for change in result.get("changes", []):
            print(f"    {change}")
        weakest = result.get("weakest_classes")
        if weakest:
            print(f"    weakest: {weakest['before']} -> {weakest['after']}")

    if args.json_out:
        args.json_out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nreport: {args.json_out}")

    failed = [item for item in results if item.get("error")]
    changed = [item for item in results if item.get("class_rows_changed")]
    print(f"\nsummary: {len(results)} runs, {len(changed)} with changed rows, {len(failed)} errors, applied={args.apply}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
