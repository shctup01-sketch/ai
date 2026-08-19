"""웹에서 정보를 검색하는 Tool.

이 Tool 자체는 인터넷에 접근할 능력이 전혀 없다 - 입력을 검증한 뒤
주입받은 WebSearchProvider에게 그대로 위임할 뿐이다. 실제 네트워크
권한은 향후 WebSearchProvider 구현체가 담당한다. Permission(SAFE/
CAUTION/DANGEROUS, requires_approval) 판단도 이 Tool의 책임이 아니다 -
그건 PermissionManager가 외부에서 관리한다.
"""

from .tool import Tool
from .web_search_provider import WebSearchProvider

DEFAULT_MAX_RESULTS = 5


class WebSearchToolError(Exception):
    """query/max_results 입력이 유효하지 않을 때 발생한다."""


class WebSearchTool(Tool):
    """주입받은 WebSearchProvider에게 실제 검색을 위임하는 Tool."""

    name = "web_search"
    description = "웹에서 정보를 검색합니다."

    def __init__(self, provider: WebSearchProvider):
        self._provider = provider

    def execute(self, **kwargs) -> object:
        query = kwargs.get("query")
        if not isinstance(query, str) or not query.strip():
            raise WebSearchToolError(f"query는 비어 있지 않은 문자열이어야 합니다: {query!r}")

        max_results = kwargs.get("max_results", DEFAULT_MAX_RESULTS)
        # bool은 파이썬에서 int의 하위 타입이므로(isinstance(True, int) == True)
        # bool 검사를 int 검사보다 먼저 해야 True/False가 유효한 max_results로
        # 잘못 받아들여지지 않는다.
        if isinstance(max_results, bool) or not isinstance(max_results, int) or max_results < 1:
            raise WebSearchToolError(f"max_results는 1 이상의 정수여야 합니다: {max_results!r}")

        # Provider가 반환한 결과를 수정/요약하지 않고 그대로 반환한다.
        return self._provider.search(query, max_results=max_results)
