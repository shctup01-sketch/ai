"""Task -> WorkerRegistry -> Worker -> 결과 -> TaskManager 상태 반영 흐름을
담당하는 범용 실행 조정자.

TaskExecutor는 "어느 Worker에게 보낼지"만 담당한다. Tool 실행 계층은
알지 못한다 — Tool/ToolRegistry/ToolExecutor/PermissionManager는 import하지
않는다. Worker가 Tool을 쓸 때 거치는 WorkerContext는 TaskExecutor가
생성하지 않고 외부에서 주입받아 그대로 Worker에게 넘길 뿐이며, 그 안에서
무슨 일이 일어나는지는 TaskExecutor의 관심사가 아니다. task_type도 특정
값을 하드코딩하지 않고, 항상 WorkerRegistry를 통해 동적으로 조회한다.

46단계 - execute_task(on_progress=None)는 그대로 worker.execute()에
넘겨줄 뿐이다(Worker.execute()가 이미 이 선택적 매개변수를 받는다) -
TaskExecutor 자신은 그 콜백이 무엇을 하는지, 어떤 task_type이 실제로
쓰는지 전혀 알지 못한다(여전히 특정 task_type을 하드코딩하지 않는다).
"""

from typing import Callable

from .task import Task
from .task_manager import TaskManager
from .worker_context import WorkerContext
from .worker_registry import WorkerNotFoundError, WorkerRegistry

_EXECUTABLE_STATUS = "planned"
_IN_PROGRESS_STEP = "worker 실행 중"


class TaskExecutionError(Exception):
    """TaskExecutor 관련 오류의 공통 기반."""


class TaskAlreadyStartedError(TaskExecutionError):
    """이미 시작되었거나 끝난 Task를 다시 실행하려 할 때 발생한다."""


class TaskExecutor:
    """Task를 받아 적절한 Worker에게 실행을 위임하고 결과를 TaskManager에 반영한다.

    TaskManager/WorkerRegistry/WorkerContext는 외부에서 주입받는다 — Studio
    전체에서 각각 하나의 인스턴스를 공유할 수 있어야 하므로 TaskExecutor
    내부에서 새로 만들지 않는다.
    """

    def __init__(
        self,
        task_manager: TaskManager,
        worker_registry: WorkerRegistry,
        worker_context: WorkerContext,
    ):
        self._task_manager = task_manager
        self._worker_registry = worker_registry
        self._worker_context = worker_context

    def execute_task(self, task_id: str, on_progress: Callable[[str], None] | None = None) -> Task:
        # 존재하지 않는 task_id면 TaskManager.get_task()의 TaskNotFoundError가
        # 그대로 전파된다 - 여기서 새 Task를 만들거나 삼키지 않는다.
        task = self._task_manager.get_task(task_id)

        if task.status != _EXECUTABLE_STATUS:
            raise TaskAlreadyStartedError(
                "이미 시작되었거나 끝난 Task는 다시 실행할 수 없습니다: "
                f"task_id={task_id}, status={task.status}"
            )

        try:
            worker = self._worker_registry.get_worker(task.task_type)
        except WorkerNotFoundError as exc:
            # Worker 미등록 상태에서는 실제 실행이 없었으므로 in_progress를
            # 거치지 않고 곧바로 실패로 처리한다.
            return self._task_manager.fail_task(task_id, str(exc))

        self._task_manager.update_status(task_id, "in_progress", current_step=_IN_PROGRESS_STEP)

        try:
            result = worker.execute(task, self._worker_context, on_progress=on_progress)
        except Exception as exc:
            # Worker의 일반적인 작업 실패로 Studio 전체가 죽으면 안 된다.
            # context.execute_tool()에서 나온 ToolApprovalRequiredError 같은
            # 예외도 여기서는 특별 취급하지 않고 동일하게 실패로 기록한다 -
            # 승인 UI/재개(resume) 구조는 이번 단계의 범위가 아니다.
            # KeyboardInterrupt/SystemExit 등 BaseException 계열은 Exception이
            # 아니므로 여기서 잡히지 않고 그대로 전파된다.
            return self._task_manager.fail_task(task_id, str(exc))

        # Worker가 반환한 object는 해석/변환하지 않고 그대로 저장한다.
        return self._task_manager.complete_task(task_id, result)
