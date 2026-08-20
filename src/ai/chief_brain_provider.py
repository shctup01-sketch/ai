"""Chief Brain 제공자 공통 인터페이스.

기존 AIProvider(provider.py)와 분리한다 - AIProvider.send_message()는
단일 BrainResponse를 돌려주는 지금의 Brain 계약이고, 이 인터페이스는
여러 단계로 이루어질 수 있는 ChiefBrainPlan을 돌려주는 별개의 계약이다.
서로 대체하지 않고 나란히 존재한다.
"""

from abc import ABC, abstractmethod

from .chief_brain_plan import ChiefBrainPlan


class ChiefBrainProvider(ABC):
    """메시지 목록을 주면 구조화된 Chief Brain 계획을 돌려준다."""

    @abstractmethod
    def plan_work(self, messages: list[dict]) -> ChiefBrainPlan:
        raise NotImplementedError
