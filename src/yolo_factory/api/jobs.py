import uuid
import threading
from typing import Callable, Any, Dict
from pydantic import BaseModel

class JobStatus(BaseModel):
    id: str
    status: str  # "pending", "running", "completed", "failed"
    progress: float  # 0.0 to 100.0
    message: str
    payload: Any = None

class JobTracker:
    def __init__(self):
        self._jobs: Dict[str, JobStatus] = {}
        self._lock = threading.Lock()

    def create_job(self, message: str = "任务排队中") -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = JobStatus(
                id=job_id,
                status="pending",
                progress=0.0,
                message=message
            )
        return job_id

    def update_job(self, job_id: str, status: str = None, progress: float = None, message: str = None, payload: Any = None):
        with self._lock:
            if job_id not in self._jobs:
                return
            job = self._jobs[job_id]
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = progress
            if message is not None:
                job.message = message
            if payload is not None:
                job.payload = payload

    def get_job(self, job_id: str) -> JobStatus | None:
        with self._lock:
            return self._jobs.get(job_id)

    def start_background_task(self, target: Callable[[str, Any], None], args: Any = None, message: str = "正在执行后台任务"):
        job_id = self.create_job(message)

        def wrapper():
            try:
                self.update_job(job_id, status="running", progress=0.0, message=message)
                target(job_id, args)
                self.update_job(job_id, status="completed", progress=100.0, message="任务已完成")
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.update_job(job_id, status="failed", progress=0.0, message=f"任务执行失败: {str(e)}")

        t = threading.Thread(target=wrapper, daemon=True)
        t.start()
        return job_id

# Global instance
job_tracker = JobTracker()
