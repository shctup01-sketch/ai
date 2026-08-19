"""웹 검색 실행부를 특정 검색 서비스로부터 분리하는 추상 인터페이스.

WebSearchTool은 이 인터페이스에만 의존한다. Google/Bing/Brave/Tavily 등
특정 검색 서비스에 종속되지 않고, 나중에 검색 공급자를 자유롭게 교체할
수 있게 하기 위함이다. 이번 단계에서는 구현체를 만들지 않는다.
"""

from abc import ABC, abstractmethod


class WebSearchProvider(ABC):
    """실제 웹 검색을 수행하는 공급자의 공통 계약."""

    @abstractmethod
    def search(self, query: str, *, max_results: int = 5) -> list[dict]:
        """query로 검색하고, 최대 max_results개의 결과를 돌려준다."""
        raise NotImplementedError
