from sqlalchemy.orm import Session

from yolo_factory.registry.models import Task


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, task: Task) -> None:
        self._session.add(task)

    def get(self, task_id: str) -> Task | None:
        return self._session.get(Task, task_id)
