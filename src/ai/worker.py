"""Worker(작업 수행자)의 공통 인터페이스.

Worker는 특정 task_type의 작업을 실제로 수행하는 주체다. TaskManager나
MainWindow를 직접 소유하거나 호출하지 않는다 — Task를 받아 작업하고
결과를 반환하는 것까지만이 Worker의 책임이다. 이번 단계에서는 이
공통 인터페이스만 정의하고, 실제 작업을 수행하는 구체 Worker(Developer,
Research 등)는 만들지 않는다.

Worker가 Tool을 쓸 때는 반드시 execute()로 전달되는 WorkerContext를
통해서만 접근한다 — ToolExecutor/ToolRegistry/PermissionManager를
직접 import하거나 소유하지 않는다.
"""

from abc import ABC, abstractmethod

from .task import Task
from .worker_context import WorkerContext


class Worker(ABC):
    """모든 Worker가 따라야 하는 최소 규격."""

    task_type: str

    @abstractmethod
    def execute(self, task: Task, context: WorkerContext) -> object:
        """task를 실제로 수행하고 결과를 반환한다.

        Tool이 필요하면 context.execute_tool(...)로만 접근한다.
        """
        raise NotImplementedError
