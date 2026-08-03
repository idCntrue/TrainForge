import logging
import threading
from collections.abc import Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PeriodicAction:
    name: str
    interval_seconds: float
    action: Callable[[], object]


class ApplicationLifecycle:
    def __init__(
        self,
        *,
        startup_actions: Sequence[Callable[[], object]],
        periodic_actions: Sequence[PeriodicAction],
    ) -> None:
        self._startup_actions = tuple(startup_actions)
        self._periodic_actions = tuple(periodic_actions)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._stop.clear()
        for action in self._startup_actions:
            action()
        self._threads = [self._start_periodic(action) for action in self._periodic_actions]
        self._running = True

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=2)
        self._threads.clear()
        self._running = False

    def _start_periodic(self, periodic: PeriodicAction) -> threading.Thread:
        if periodic.interval_seconds <= 0:
            raise ValueError(f"periodic action {periodic.name} requires a positive interval")

        def run() -> None:
            while not self._stop.wait(periodic.interval_seconds):
                try:
                    periodic.action()
                except Exception:
                    logger.exception("periodic action failed: %s", periodic.name)

        thread = threading.Thread(target=run, name=f"trainforge-{periodic.name}", daemon=True)
        thread.start()
        return thread


def lifespan_for(runtime: ApplicationLifecycle):
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime.start()
        try:
            yield
        finally:
            runtime.stop()

    return lifespan
