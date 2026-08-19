from abc import ABC, abstractmethod

from .developer_request import DeveloperRequest
from .developer_result import DeveloperResult


class DeveloperProvider(ABC):
    """Developer 제공자 공통 인터페이스.

    Brain의 AIProvider와는 의도적으로 분리했다. Brain은 대화 한 번에
    구조화된 응답 하나를 돌려주는 단순한 패턴이지만, Developer는 도구
    호출을 여러 번 주고받는 반복 패턴이라 통신 방식 자체가 다르다.
    """

    @abstractmethod
    def build_project(self, request: DeveloperRequest) -> DeveloperResult:
        raise NotImplementedError
