from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from enum import Enum


class TaskStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskRecord:
    task_id: str
    description: str
    future: Future


class TaskManager:
    def __init__(self, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def spawn(self, description: str, fn: object, *args: object) -> str:
        with self._lock:
            self._counter += 1
            task_id = f"task_{self._counter}"
        future = self._executor.submit(fn, *args)
        record = TaskRecord(task_id=task_id, description=description, future=future)
        with self._lock:
            self._tasks[task_id] = record
        return task_id

    def status(self, task_id: str) -> tuple[TaskStatus, str]:
        with self._lock:
            record = self._tasks.get(task_id)
        if record is None:
            return TaskStatus.FAILED, f"Unknown task ID: {task_id}"
        if record.future.done():
            exc = record.future.exception()
            if exc is not None:
                return TaskStatus.FAILED, f"Error: {exc}"
            return TaskStatus.COMPLETED, record.description
        return TaskStatus.RUNNING, record.description

    def get_result(self, task_id: str, timeout: float | None = None) -> str:
        with self._lock:
            record = self._tasks.get(task_id)
        if record is None:
            return f"Unknown task ID: {task_id}"
        try:
            result = record.future.result(timeout=timeout)
            return result or "(sub-agent produced no output)"
        except FuturesTimeoutError:
            return f"Task {task_id} is still running (timed out after {timeout}s)."
        except Exception as exc:
            return f"Task {task_id} failed: {exc}"

    def list_tasks(self) -> list[tuple[str, str, TaskStatus]]:
        with self._lock:
            records = list(self._tasks.values())
        result = []
        for r in records:
            status, _ = self.status(r.task_id)
            result.append((r.task_id, r.description, status))
        return result

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
