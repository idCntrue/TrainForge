import pytest

from yolo_factory.annotations.geometry import GeometryError, validate_box, validate_polygon


def test_accepts_normalized_box_and_polygon() -> None:
    assert validate_box([0.5, 0.5, 0.25, 0.2]) == [0.5, 0.5, 0.25, 0.2]
    assert validate_polygon([0.1, 0.1, 0.8, 0.1, 0.5, 0.8]) == [0.1, 0.1, 0.8, 0.1, 0.5, 0.8]


def test_clamps_only_negligible_floating_point_noise() -> None:
    assert validate_polygon([-5e-8, 0.1, 1.0 + 5e-8, 0.1, 0.5, 0.8]) == [0.0, 0.1, 1.0, 0.1, 0.5, 0.8]

    with pytest.raises(GeometryError, match="normalized"):
        validate_polygon([-1e-4, 0.1, 0.8, 0.1, 0.5, 0.8])


@pytest.mark.parametrize("coordinates", [[-0.1, 0.5, 0.2, 0.2], [0.5, 0.5, 0.0, 0.2], [0.95, 0.5, 0.2, 0.2]])
def test_rejects_invalid_boxes(coordinates: list[float]) -> None:
    with pytest.raises(GeometryError):
        validate_box(coordinates)


def test_rejects_self_intersecting_or_tiny_polygon() -> None:
    with pytest.raises(GeometryError, match="self-intersects"):
        validate_polygon([0.1, 0.1, 0.9, 0.9, 0.1, 0.9, 0.9, 0.1])
    with pytest.raises(GeometryError, match="area"):
        validate_polygon([0.1, 0.1, 0.10001, 0.1, 0.1, 0.10001])
