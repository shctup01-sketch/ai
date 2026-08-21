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
from typing import Callable

from .task import Task
from .worker_context import WorkerContext


class Worker(ABC):
    """모든 Worker가 따라야 하는 최소 규격.

    46단계 - on_progress는 이 작업이 내부적으로 얼마나 진행됐는지(예:
    ResearchWorker의 검색 N/M 진행)를 사람이 읽을 짧은 문장으로 알리는
    선택적 콜백이다. 기본값 None이라 기존 호출부(execute(task, context))는
    전혀 바꿀 필요가 없다 - 이 콜백을 쓰지 않는 Worker는 그냥 무시하면
    된다. PySide6/Qt Signal이 아니라 순수 Callable이다.
    """

    task_type: str

    @abstractmethod
    def execute(
        self, task: Task, context: WorkerContext, on_progress: Callable[[str], None] | None = None
    ) -> object:
        """task를 실제로 수행하고 결과를 반환한다.

        Tool이 필요하면 context.execute_tool(...)로만 접근한다.
        """
        raise NotImplementedError
