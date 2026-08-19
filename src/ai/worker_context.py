"""Worker에게 제공되는 안전한 작업 실행 환경.

WorkerContext는 Worker가 ToolRegistry나 PermissionManager에 직접 접근하지
않고, 오직 ToolExecutor를 통해서만 Tool을 실행하도록 강제하는 얇은 중간
계층이다. 이 파일 자체는 어떤 정책 판단(승인 필요 여부, 위험도 등)도
하지 않는다 - 그 책임은 전부 ToolExecutor/PermissionManager에 있다.
"""

from .tool_executor import ToolExecutor


class WorkerContext:
    """Worker가 Tool을 실행할 때 거치는 유일한 통로.

    ToolExecutor는 외부에서 주입받는다 - WorkerContext 내부에서 새로
    만들지 않는다.
    """

    def __init__(self, tool_executor: ToolExecutor):
        self._tool_executor = tool_executor

    def execute_tool(self, tool_name: str, *, approved: bool = False, **kwargs) -> object:
        # ToolExecutor.execute_tool()에 그대로 위임한다. 여기서 어떤 값도
        # 가공하거나 예외를 가로채지 않는다 - 보안 검사를 우회할 방법이
        # 없어야 한다.
        return self._tool_executor.execute_tool(tool_name, approved=approved, **kwargs)
