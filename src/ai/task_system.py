"""지금까지 독립적으로 만든 Task/Worker/Tool/Permission 계층을 한 곳에서
조립하는 구성 계층.

이 파일 하나만 "research"라는 구체 task_type과 "web_search"라는 구체
Tool 이름을 알고 있다 - TaskManager/TaskExecutor/WorkerRegistry/
ToolRegistry/ToolExecutor/PermissionManager/WorkerContext 자체는
여전히 어떤 task_type/Tool 이름도 하드코딩하지 않은 범용 계층으로
남아 있다.

OpenAI client는 생성자에서 외부 주입만 받는다 - 이 파일 안에서
OpenAI()를 생성하거나 API Key/환경변수/.env를 직접 다루지 않는다.

MainWindow/GUI/QThread/Scheduler/DB 어디와도 아직 연결하지 않는다.
"""

from typing import Any, Callable

from .openai_web_search_provider import OpenAIWebSearchProvider
from .permission import PermissionLevel, ToolPermission
from .permission_manager import PermissionManager
from .research_worker import ResearchWorker
from .task import Task
from .task_executor import TaskExecutor
from .task_manager import TaskManager
from .tool_executor import ToolExecutor
from .tool_registry import ToolRegistry
from .web_search_tool import WebSearchTool
from .worker_context import WorkerContext
from .worker_registry import WorkerRegistry

WEB_SEARCH_PERMISSION_REASON = (
    "웹 검색은 외부 서비스에 검색 요청을 전송하지만 로컬 파일이나 계정을 변경하지 않습니다."
)


class TaskSystem:
    """Task/Worker/Tool/Permission 계층을 조립해 실제로 쓸 수 있게 만든다."""

    def __init__(self, openai_client: Any):
        self.task_manager = TaskManager()
        self.worker_registry = WorkerRegistry()
        self.tool_registry = ToolRegistry()
        self.permission_manager = PermissionManager()

        self.web_search_provider = OpenAIWebSearchProvider(client=openai_client)
        web_search_tool = WebSearchTool(provider=self.web_search_provider)
        self.tool_registry.register(web_search_tool)
        self.permission_manager.register_permission(
            ToolPermission(
                tool_name=web_search_tool.name,
                level=PermissionLevel.CAUTION,
                requires_approval=False,
                reason=WEB_SEARCH_PERMISSION_REASON,
            )
        )

        self.tool_executor = ToolExecutor(
            tool_registry=self.tool_registry,
            permission_manager=self.permission_manager,
        )
        self.worker_context = WorkerContext(tool_executor=self.tool_executor)

        self.worker_registry.register(ResearchWorker())

        self.task_executor = TaskExecutor(
            task_manager=self.task_manager,
            worker_registry=self.worker_registry,
            worker_context=self.worker_context,
        )

    def create_task(self, task_type: str, title: str, goal: str) -> Task:
        return self.task_manager.create_task(task_type=task_type, title=title, goal=goal)

    def execute_task(self, task_id: str, on_progress: Callable[[str], None] | None = None) -> Task:
        # 46단계 - task_executor.execute_task()로 그대로 전달한다(§6, 새
        # 이벤트 시스템을 만들지 않는다).
        return self.task_executor.execute_task(task_id, on_progress=on_progress)
