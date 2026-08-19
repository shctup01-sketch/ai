"""Tool 이름 문자열 -> Tool 매핑만 담당하는 레지스트리.

ToolRegistry는 Tool 이름의 의미를 전혀 해석하지 않는다. web_search나
read_file 같은 이름을 특별 취급하지 않고, 어떤 이름이 들어와도 동일한
방식으로 등록/조회한다. 새로운 Tool이 추가되어도 이 파일은 수정할
필요가 없다.
"""

from .tool import Tool


class ToolRegistryError(Exception):
    """ToolRegistry 관련 오류의 공통 기반."""


class DuplicateToolError(ToolRegistryError):
    """이미 등록된 name에 다시 Tool을 등록하려 할 때 발생한다."""


class ToolNotFoundError(ToolRegistryError):
    """등록되지 않은 name의 Tool을 찾으려 할 때 발생한다."""


class ToolRegistry:
    """Tool.name -> Tool 매핑을 메모리에서 관리한다."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(f"이미 등록된 Tool 이름입니다: {tool.name}")
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"등록되지 않은 Tool 이름입니다: {name}") from None

    def has_tool(self, name: str) -> bool:
        return name in self._tools

    def list_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def unregister(self, name: str) -> None:
        try:
            del self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"등록되지 않은 Tool 이름입니다: {name}") from None
