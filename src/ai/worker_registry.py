"""task_type 문자열 -> Worker 매핑만 담당하는 레지스트리.

WorkerRegistry는 task_type의 의미를 전혀 해석하지 않는다. "development"나
"research"를 특별 취급하지 않고, 어떤 문자열이 들어와도 동일한 방식으로
등록/조회한다. 새로운 Worker가 추가되어도 이 파일은 수정할 필요가 없다.
"""

from .worker import Worker


class WorkerRegistryError(Exception):
    """WorkerRegistry 관련 오류의 공통 기반."""


class DuplicateWorkerError(WorkerRegistryError):
    """이미 등록된 task_type에 다시 Worker를 등록하려 할 때 발생한다."""


class WorkerNotFoundError(WorkerRegistryError):
    """등록되지 않은 task_type의 Worker를 찾으려 할 때 발생한다."""


class WorkerRegistry:
    """task_type -> Worker 매핑을 메모리에서 관리한다."""

    def __init__(self):
        self._workers: dict[str, Worker] = {}

    def register(self, worker: Worker) -> None:
        if worker.task_type in self._workers:
            raise DuplicateWorkerError(
                f"이미 등록된 task_type입니다: {worker.task_type}"
            )
        self._workers[worker.task_type] = worker

    def get_worker(self, task_type: str) -> Worker:
        try:
            return self._workers[task_type]
        except KeyError:
            raise WorkerNotFoundError(
                f"등록되지 않은 task_type입니다: {task_type}"
            ) from None

    def has_worker(self, task_type: str) -> bool:
        return task_type in self._workers

    def list_task_types(self) -> list[str]:
        return list(self._workers.keys())

    def unregister(self, task_type: str) -> None:
        try:
            del self._workers[task_type]
        except KeyError:
            raise WorkerNotFoundError(
                f"등록되지 않은 task_type입니다: {task_type}"
            ) from None
