"""Tool 이름 문자열 -> ToolPermission 매핑과 그 판단 엔진.

기본 거부 원칙: 정책이 등록되지 않은 Tool은 SAFE로 간주하거나 자동
허용하지 않는다. "정책 없음"은 "안전함"이 아니라 "판단할 수 없음"이며,
이 경우 항상 명확한 예외를 발생시킨다. 어떤 메서드도 이 원칙을 우회해
조용히 기본값을 돌려주지 않는다.
"""

from .permission import PermissionLevel, ToolPermission


class PermissionManagerError(Exception):
    """PermissionManager 관련 오류의 공통 기반."""


class DuplicatePermissionError(PermissionManagerError):
    """이미 등록된 tool_name에 다시 정책을 등록하려 할 때 발생한다."""


class PermissionNotFoundError(PermissionManagerError):
    """등록되지 않은 tool_name의 정책을 찾으려 할 때 발생한다."""


class PermissionManager:
    """tool_name -> ToolPermission 매핑을 메모리에서 관리한다."""

    def __init__(self):
        self._permissions: dict[str, ToolPermission] = {}

    def register_permission(self, permission: ToolPermission) -> None:
        if permission.tool_name in self._permissions:
            raise DuplicatePermissionError(
                f"이미 등록된 tool_name입니다: {permission.tool_name}"
            )
        self._permissions[permission.tool_name] = permission

    def get_permission(self, tool_name: str) -> ToolPermission:
        try:
            return self._permissions[tool_name]
        except KeyError:
            raise PermissionNotFoundError(
                f"등록되지 않은 tool_name입니다: {tool_name}"
            ) from None

    def has_permission(self, tool_name: str) -> bool:
        return tool_name in self._permissions

    def requires_approval(self, tool_name: str) -> bool:
        return self.get_permission(tool_name).requires_approval

    def get_level(self, tool_name: str) -> PermissionLevel:
        return self.get_permission(tool_name).level

    def list_permissions(self) -> list[ToolPermission]:
        return list(self._permissions.values())

    def unregister_permission(self, tool_name: str) -> None:
        try:
            del self._permissions[tool_name]
        except KeyError:
            raise PermissionNotFoundError(
                f"등록되지 않은 tool_name입니다: {tool_name}"
            ) from None
