"""범용 Worker/Tool 구조 위의 첫 번째 실제 Worker.

ResearchWorker는 Task의 title/goal로 검색어를 만들고, WorkerContext를
통해 web_search Tool을 호출해 검색 결과를 그대로 담아 반환한다.
ToolExecutor/ToolRegistry/PermissionManager/WebSearchTool/
WebSearchProvider는 직접 알지 못한다 - Tool 호출은 오직 WorkerContext를
거친다. 승인 여부도 스스로 결정하지 않는다(approved를 임의로 True로
보내지 않음) - 그건 PermissionManager의 책임이다. 검색 결과를 요약하거나
market_size/competitors/recommendation 같은 분석 데이터를 만들어내지
않는다 - 그건 향후 별도의 분석 단계가 할 일이다.
"""

from .task import Task
from .worker import Worker
from .worker_context import WorkerContext

RESEARCH_TASK_TYPE = "research"
WEB_SEARCH_TOOL_NAME = "web_search"
DEFAULT_MAX_RESULTS = 5


class ResearchWorkerError(Exception):
    """ResearchWorker가 처리할 수 없는 Task가 들어왔을 때 발생한다."""


class ResearchWorker(Worker):
    """조사(research) 작업을 위해 web_search Tool을 호출하는 Worker."""

    task_type = RESEARCH_TASK_TYPE

    def execute(self, task: Task, context: WorkerContext) -> object:
        if task.task_type != self.task_type:
            raise ResearchWorkerError(
                f"ResearchWorker는 task_type='{self.task_type}'만 처리할 수 있습니다: "
                f"받은 값={task.task_type}"
            )

        query = f"{task.title} {task.goal}".strip()

        # approved를 전달하지 않는다(기본값 False) - 승인이 필요한 Tool이라면
        # ToolApprovalRequiredError가 그대로 이 아래에서 발생해 전파된다.
        # ToolApprovalRequiredError/PermissionNotFoundError/ToolNotFoundError/
        # WebSearchToolError/Provider의 일반 예외를 여기서 잡아 가짜 성공
        # 결과로 바꾸지 않는다.
        search_results = context.execute_tool(
            WEB_SEARCH_TOOL_NAME,
            query=query,
            max_results=DEFAULT_MAX_RESULTS,
        )

        return {
            "task_type": task.task_type,
            "title": task.title,
            "goal": task.goal,
            "query": query,
            "search_results": search_results,
        }
