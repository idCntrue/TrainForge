from pathlib import Path

from yolo_factory.api.jobs import JobTracker
from yolo_factory.registry.database import create_registry


def test_jobs_are_visible_across_tracker_instances(tmp_path: Path) -> None:
    registry = create_registry(tmp_path / "factory.db")
    first = JobTracker(registry)
    job_id = first.create_job("Queued")
    first.update_job(job_id, status="running", progress=25, payload={"step": 1})

    restored = JobTracker(registry).get_job(job_id)

    assert restored is not None
    assert restored.status == "running"
    assert restored.progress == 25
    assert restored.payload == {"step": 1}


def test_startup_recovery_marks_abandoned_jobs_interrupted(tmp_path: Path) -> None:
    registry = create_registry(tmp_path / "factory.db")
    tracker = JobTracker(registry)
    pending = tracker.create_job("Pending")
    running = tracker.create_job("Running")
    tracker.update_job(running, status="running")

    recovered = JobTracker(registry).recover_interrupted()

    assert set(recovered) == {pending, running}
    assert tracker.get_job(pending).status == "interrupted"
    assert tracker.get_job(running).status == "interrupted"


def test_lists_jobs_with_status_limit_and_offset(tmp_path: Path) -> None:
    tracker = JobTracker(create_registry(tmp_path / "factory.db"))
    ids = [tracker.create_job(f"job {index}") for index in range(4)]
    tracker.update_job(ids[3], status="completed")

    listed = tracker.list_jobs(status="pending", limit=2, offset=1)

    assert [job.id for job in listed] == [ids[1], ids[0]]
