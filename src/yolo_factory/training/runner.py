import argparse
import json
import signal
import time
import traceback as traceback_module
from datetime import datetime, timezone
from pathlib import Path


_cancelled = False


class TrainingCancelled(RuntimeError):
    pass


def _request_cancel(signum: int, frame: object) -> None:
    del signum, frame
    global _cancelled
    _cancelled = True


def _write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _append_event(path: Path, payload: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, sort_keys=True) + "\n")


def run(manifest_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    run_directory = manifest_path.parent
    progress_path = run_directory / "progress.jsonl"
    heartbeat_path = run_directory / "heartbeat.json"
    runtime_state = {"phase": "preparing", "epoch": None, "total_epochs": None}

    def emit(payload: dict) -> None:
        if _cancelled:
            raise TrainingCancelled("Cancellation requested")
        now = datetime.now(timezone.utc).isoformat()
        event = {**payload, "timestamp": payload.get("timestamp", now)}
        runtime_state["phase"] = event.get("phase", runtime_state["phase"])
        if event.get("epoch") is not None:
            runtime_state["epoch"] = event["epoch"]
        if event.get("total_epochs") is not None:
            runtime_state["total_epochs"] = event["total_epochs"]
        _write_json(heartbeat_path, {"run_id": manifest["run_id"], "timestamp": event["timestamp"]})
        _append_event(progress_path, event)

    if manifest["engine"] == "ultralytics":
        try:
            from yolo_factory.training.ultralytics_adapter import run_ultralytics

            emit({"status": "running", "phase": "preparing", "progress": 2.0, "message": "Preparing Ultralytics training"})
            run_ultralytics(manifest, run_directory, emit)
            return 0
        except TrainingCancelled:
            _append_event(progress_path, {"status": "cancelled", "phase": "cancelled", "progress": 0.0, "message": "Cancellation requested", "timestamp": datetime.now(timezone.utc).isoformat()})
            return 2
        except Exception as exc:
            _append_event(progress_path, {
                "status": "failed",
                "phase": runtime_state["phase"],
                "progress": 0.0,
                "message": f"{type(exc).__name__}: {exc}",
                "technical_message": str(exc),
                "exception_type": type(exc).__name__,
                "traceback": traceback_module.format_exc(),
                "last_successful_epoch": runtime_state["epoch"],
                "total_epochs": runtime_state["total_epochs"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            return 1
    if manifest["engine"] != "simulation":
        raise ValueError(f"unsupported training engine: {manifest['engine']}")

    delay = float(manifest["simulation_step_seconds"])
    stages = [
        ("running", "training", 8.0, "Runner started"),
        ("running", "training", 55.0, "Simulated epochs complete"),
        ("evaluating", "evaluation", 75.0, "Metrics parsed"),
        ("exporting", "export", 87.0, "ONNX export complete"),
        ("verifying", "verification", 96.0, "PT/ONNX consistency passed"),
        ("completed", "completed", 100.0, "Training release gates passed"),
    ]
    for status, phase, progress, message in stages:
        if _cancelled:
            _append_event(progress_path, {"status": "cancelled", "phase": "cancelled", "progress": progress, "message": "Cancellation requested"})
            return 2
        emit({"status": status, "phase": phase, "progress": progress, "message": message})
        time.sleep(delay)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _request_cancel)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _request_cancel)
    return run(args.manifest)


if __name__ == "__main__":
    raise SystemExit(main())
