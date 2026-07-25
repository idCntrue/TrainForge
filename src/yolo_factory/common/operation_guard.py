from __future__ import annotations

import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from yolo_factory.registry.database import Registry, session_scope
from yolo_factory.registry.models import HeavyOperationLeaseRecord


class ActiveHeavyOperationError(RuntimeError):
    pass


class HeavyOperationGuard:
    def __init__(self, registry: Registry | None = None, *, lease_seconds: float = 60) -> None:
        self._registry = registry
        self._lease_seconds = lease_seconds
        self._lock = threading.Lock()
        self._local_operation: str | None = None
        self._owner_id = uuid.uuid4().hex

    @property
    def active_operation(self) -> str | None:
        if self._registry is None:
            return self._local_operation
        with session_scope(self._registry) as session:
            lease = session.get(HeavyOperationLeaseRecord, "global")
            return lease.operation if lease is not None and _as_utc(lease.expires_at) > datetime.now(timezone.utc) else None

    @contextmanager
    def acquire(self, operation: str):
        if self._registry is None:
            if not self._lock.acquire(blocking=False):
                raise ActiveHeavyOperationError(f"heavy operation already active: {self._local_operation}")
            self._local_operation = operation
            try:
                yield
            finally:
                self._local_operation = None
                self._lock.release()
            return

        self._acquire_lease(operation)
        stop = threading.Event()
        heartbeat = threading.Thread(
            target=self._heartbeat_loop,
            args=(stop,),
            name=f"lease-{operation}",
            daemon=True,
        )
        heartbeat.start()
        try:
            yield
        finally:
            stop.set()
            heartbeat.join(timeout=2)
            self._release_lease()

    def _acquire_lease(self, operation: str) -> None:
        now = datetime.now(timezone.utc)
        try:
            with session_scope(self._registry) as session:
                lease = session.get(HeavyOperationLeaseRecord, "global")
                if lease is not None and _as_utc(lease.expires_at) > now:
                    raise ActiveHeavyOperationError(f"heavy operation already active: {lease.operation}")
                if lease is not None:
                    session.delete(lease)
                    session.flush()
                session.add(HeavyOperationLeaseRecord(
                    key="global",
                    operation=operation,
                    owner_id=self._owner_id,
                    acquired_at=now,
                    heartbeat_at=now,
                    expires_at=now + timedelta(seconds=self._lease_seconds),
                ))
        except IntegrityError as exc:
            raise ActiveHeavyOperationError("heavy operation already active") from exc

    def _heartbeat_loop(self, stop: threading.Event) -> None:
        interval = max(0.1, self._lease_seconds / 3)
        while not stop.wait(interval):
            now = datetime.now(timezone.utc)
            with session_scope(self._registry) as session:
                lease = session.get(HeavyOperationLeaseRecord, "global")
                if lease is None or lease.owner_id != self._owner_id:
                    return
                lease.heartbeat_at = now
                lease.expires_at = now + timedelta(seconds=self._lease_seconds)

    def _release_lease(self) -> None:
        with session_scope(self._registry) as session:
            lease = session.get(HeavyOperationLeaseRecord, "global")
            if lease is not None and lease.owner_id == self._owner_id:
                session.delete(lease)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
