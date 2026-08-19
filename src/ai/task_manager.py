"""범용 Task를 메모리에서 생성/보관/조회/상태변경하는 관리자.

TaskManager는 task_type의 의미를 전혀 해석하지 않는다 — development,
research, business, file_management, automation 등 어떤 문자열이 오더라도
동일하게 관리한다. 실제 작업 수행은 이후 도입될 Worker의 몫이다.

아직 DB/파일 저장은 하지 않는다. 프로그램이 실행되는 동안 메모리에만
Task를 보관한다.
"""

import uuid

from .task import Task

_ALLOWED_STATUSES = ("planned", "in_progress", "success", "failed")


class TaskManagerError(Exception):
    """TaskManager 관련 오류의 공통 기반."""


class TaskNotFoundError(TaskManagerError):
    """존재하지 않는 task_id를 조회/변경/삭제하려 할 때 발생한다."""


class DuplicateTaskError(TaskManagerError):
    """이미 존재하는 task_id로 Task를 등록하려 할 때 발생한다."""


class InvalidTaskStatusError(TaskManagerError):
    """허용되지 않는 status로 변경하려 할 때 발생한다."""


class TaskManager:
    """메모리 기반 Task 저장소. dict[str, Task]를 내부적으로 관리한다."""

    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create_task(self, task_type: str, title: str, goal: str) -> Task:
        task_id = str(uuid.uuid4())
        task = Task(task_id=task_id, task_type=task_type, title=title, goal=goal)
        self.add_task(task)
        return task

    def add_task(self, task: Task) -> None:
        if task.task_id in self._tasks:
            raise DuplicateTaskError(f"이미 등록된 task_id입니다: {task.task_id}")
        self._tasks[task.task_id] = task

    def get_task(self, task_id: str) -> Task:
        try:
            return self._tasks[task_id]
        except KeyError:
            raise TaskNotFoundError(f"존재하지 않는 task_id입니다: {task_id}") from None

    def list_tasks(self) -> list[Task]:
        return list(self._tasks.values())

    def update_status(self, task_id: str, status: str, current_step: str | None = None) -> Task:
        if status not in _ALLOWED_STATUSES:
            raise InvalidTaskStatusError(f"허용되지 않는 status입니다: {status}")

        task = self.get_task(task_id)
        task.status = status
        if current_step is not None:
            task.current_step = current_step
        return task

    def complete_task(self, task_id: str, result: object) -> Task:
        task = self.get_task(task_id)
        task.status = "success"
        task.result = result
        return task

    def fail_task(self, task_id: str, error: str) -> Task:
        task = self.get_task(task_id)
        task.status = "failed"
        task.errors.append(error)
        return task

    def remove_task(self, task_id: str) -> None:
        try:
            del self._tasks[task_id]
        except KeyError:
            raise TaskNotFoundError(f"존재하지 않는 task_id입니다: {task_id}") from None
