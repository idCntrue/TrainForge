from time import sleep

from yolo_factory.operations.lifecycle import ApplicationLifecycle, PeriodicAction


def test_lifecycle_runs_recovery_once_and_stops_cleanup_thread() -> None:
    events: list[str] = []
    lifecycle = ApplicationLifecycle(
        startup_actions=[lambda: events.append("recover")],
        periodic_actions=[PeriodicAction("recycle", 0.01, lambda: events.append("purge"))],
    )

    lifecycle.start()
    lifecycle.start()
    sleep(0.03)
    lifecycle.stop()

    assert events.count("recover") == 1
    assert "purge" in events
    assert lifecycle.running is False
