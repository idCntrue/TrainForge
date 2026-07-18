class GeometryError(ValueError):
    pass


_NORMALIZATION_EPSILON = 1e-7


def _normalized(values: list[float]) -> list[float]:
    coordinates = [float(value) for value in values]
    if any(value < -_NORMALIZATION_EPSILON or value > 1.0 + _NORMALIZATION_EPSILON for value in coordinates):
        raise GeometryError("coordinates must be normalized to [0, 1]")
    return [min(1.0, max(0.0, value)) for value in coordinates]


def validate_box(values: list[float]) -> list[float]:
    coordinates = _normalized(values)
    if len(coordinates) != 4:
        raise GeometryError("box requires x_center, y_center, width and height")
    x, y, width, height = coordinates
    if width <= 0 or height <= 0:
        raise GeometryError("box width and height must be positive")
    if x - width / 2 < 0 or x + width / 2 > 1 or y - height / 2 < 0 or y + height / 2 > 1:
        raise GeometryError("box exceeds image bounds")
    return coordinates


def _orientation(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(a, b, c, d) -> bool:
    return _orientation(a, b, c) * _orientation(a, b, d) < 0 and _orientation(c, d, a) * _orientation(c, d, b) < 0


def validate_polygon(values: list[float]) -> list[float]:
    coordinates = _normalized(values)
    if len(coordinates) < 6 or len(coordinates) % 2:
        raise GeometryError("polygon requires at least three points")
    points = list(zip(coordinates[::2], coordinates[1::2]))
    if len(set(points)) < 3:
        raise GeometryError("polygon requires three distinct points")
    edges = [(points[index], points[(index + 1) % len(points)]) for index in range(len(points))]
    for first, (a, b) in enumerate(edges):
        for second, (c, d) in enumerate(edges):
            if first >= second or second in {first - 1, first + 1} or {first, second} == {0, len(edges) - 1}:
                continue
            if _segments_intersect(a, b, c, d):
                raise GeometryError("polygon self-intersects")
    area = abs(sum(points[index][0] * points[(index + 1) % len(points)][1] - points[(index + 1) % len(points)][0] * points[index][1] for index in range(len(points)))) / 2
    if area < 1e-5:
        raise GeometryError("polygon area is too small")
    return coordinates


def validate_geometry(shape_type: str, values: list[float]) -> list[float]:
    if shape_type == "box":
        return validate_box(values)
    if shape_type == "polygon":
        return validate_polygon(values)
    raise GeometryError(f"unsupported shape type: {shape_type}")
