from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from yolo_factory.registry.models import Base
from yolo_factory.migrations.frame_lifecycle import migrate_frame_lifecycle
from yolo_factory.migrations.dataset_release_display_name import migrate_dataset_release_display_name
from yolo_factory.migrations.imported_models import migrate_imported_models


@dataclass(frozen=True)
class Registry:
    engine: Engine
    sessions: sessionmaker[Session]


def _enable_sqlite_constraints(
    dbapi_connection: object,
    connection_record: object,
) -> None:
    del connection_record
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


def create_registry(path: Path) -> Registry:
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path.as_posix()}", future=True)
    event.listen(engine, "connect", _enable_sqlite_constraints)
    Base.metadata.create_all(engine)
    migrate_frame_lifecycle(path)
    migrate_dataset_release_display_name(path)
    migrate_imported_models(path)
    return Registry(
        engine=engine,
        sessions=sessionmaker(bind=engine, expire_on_commit=False),
    )


@contextmanager
def session_scope(registry: Registry) -> Iterator[Session]:
    session = registry.sessions()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
