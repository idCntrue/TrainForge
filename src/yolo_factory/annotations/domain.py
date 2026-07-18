from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AnnotationShape:
    id: str
    class_id: int
    class_name: str
    shape_type: str
    coordinates: tuple[float, ...]
    source: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class AnnotationImage:
    frame_id: str
    task_id: str
    task_type: str
    image_path: str
    width: int
    height: int
    status: str
    revision: int
    classes: tuple[str, ...]
    shapes: tuple[AnnotationShape, ...]
    created_at: datetime
    updated_at: datetime
