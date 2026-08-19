"""Worker가 Tool을 쓸 때 반드시 거쳐야 하는 권한 검사 + 실행 관문.

ToolExecutor는 특정 Tool의 의미를 전혀 알지 못한다. 어떤 이름의 Tool이
오더라도 항상 같은 순서(Permission 조회 -> 승인 검사 -> Tool 조회 ->
실행)를 거친다. 승인 UI(팝업/CLI 등)는 여기서 만들지 않는다 -
ToolExecutor는 이미 결정된 approved 값만 외부로부터 받는다.
"""

from .permission_manager import PermissionManager
from .tool_registry import ToolRegistry


class ToolExecutionError(Exception):
    """ToolExecutor 관련 오류의 공통 기반."""


class ToolApprovalRequiredError(ToolExecutionError):
    """승인이 필요한 Tool을 approved=False로 실행하려 할 때 발생한다."""

    def __init__(self, tool_name: str):
        super().__init__(f"이 Tool은 사용자 승인이 필요합니다: {tool_name}")
        self.tool_name = tool_name


class ToolExecutor:
    """Permission 검사를 통과한 뒤에만 Tool을 실행하는 관문.

    ToolRegistry/PermissionManager는 외부에서 주입받는다 - ToolExecutor
    내부에서 새로 만들지 않는다.
    """

    def __init__(self, tool_registry: ToolRegistry, permission_manager: PermissionManager):
        self._tool_registry = tool_registry
        self._permission_manager = permission_manager

    def execute_tool(self, tool_name: str, *, approved: bool = False, **kwargs) -> object:
        # 1) Permission 조회가 항상 가장 먼저다. 등록되지 않았다면
        #    PermissionManager의 PermissionNotFoundError가 그대로 전파된다 -
        #    "정책 없음 = SAFE"로 간주하지 않는다.
        permission = self._permission_manager.get_permission(tool_name)

        # 2) 승인 검사. PermissionLevel 값으로 승인 여부를 추론하지 않고,
        #    저장된 requires_approval 값만 기준으로 판단한다.
        if permission.requires_approval and not approved:
            raise ToolApprovalRequiredError(tool_name)

        # 3) 여기까지 통과해야만 Tool을 조회한다 - Tool 실행이 Permission
        #    확인보다 먼저 일어날 수 없다.
        tool = self._tool_registry.get_tool(tool_name)

        # 4) Tool 실행. 여기서 발생하는 예외는 변환하지 않고 그대로
        #    호출자에게 전파한다 - Task 실패로 바꾸는 책임은 상위 계층의 몫이다.
        return tool.execute(**kwargs)
