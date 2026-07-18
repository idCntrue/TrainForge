from contextlib import contextmanager
from threading import Lock


class ActiveHeavyOperationError(RuntimeError):
    pass


class HeavyOperationGuard:
    def __init__(self) -> None:
        self._lock = Lock()
        self.active_operation: str | None = None

    @contextmanager
    def acquire(self, operation: str):
        if not self._lock.acquire(blocking=False):
            raise ActiveHeavyOperationError(f"heavy operation already active: {self.active_operation}")
        self.active_operation = operation
        try:
            yield
        finally:
            self.active_operation = None
            self._lock.release()
