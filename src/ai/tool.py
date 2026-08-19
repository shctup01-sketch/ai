"""Tool(도구)의 공통 인터페이스.

Tool은 입력을 받아 하나의 구체적인 행동을 수행하고 결과를 반환하는
독립 객체다. TaskManager, MainWindow, WorkerRegistry를 직접 소유하지
않는다. 이번 단계에서는 이 공통 인터페이스만 정의하고, 실제로 무언가를
수행하는 구체 Tool(web_search, read_file 등)은 만들지 않는다.
"""

from abc import ABC, abstractmethod


class Tool(ABC):
    """모든 Tool이 따라야 하는 최소 규격."""

    name: str
    description: str

    @abstractmethod
    def execute(self, **kwargs) -> object:
        """도구를 실행하고 결과를 반환한다."""
        raise NotImplementedError
