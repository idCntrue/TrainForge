import pytest

from yolo_factory.common.operation_guard import ActiveHeavyOperationError, HeavyOperationGuard


def test_heavy_operation_guard_rejects_overlapping_operation() -> None:
    guard = HeavyOperationGuard()
    with guard.acquire("training"):
        with pytest.raises(ActiveHeavyOperationError, match="training"):
            with guard.acquire("inference"):
                pass

    with guard.acquire("gates"):
        assert guard.active_operation == "gates"
