import pytest
from pathlib import Path

from yolo_factory.common.operation_guard import ActiveHeavyOperationError, HeavyOperationGuard
from yolo_factory.registry.database import create_registry


def test_heavy_operation_guard_rejects_overlapping_operation() -> None:
    guard = HeavyOperationGuard()
    with guard.acquire("training"):
        with pytest.raises(ActiveHeavyOperationError, match="training"):
            with guard.acquire("inference"):
                pass

    with guard.acquire("gates"):
        assert guard.active_operation == "gates"


def test_database_lease_rejects_operation_from_another_guard(tmp_path: Path) -> None:
    registry = create_registry(tmp_path / "factory.db")
    first = HeavyOperationGuard(registry, lease_seconds=30)
    second = HeavyOperationGuard(registry, lease_seconds=30)

    with first.acquire("training"):
        with pytest.raises(ActiveHeavyOperationError, match="training"):
            with second.acquire("model-gates"):
                pass

    with second.acquire("model-gates"):
        assert second.active_operation == "model-gates"
