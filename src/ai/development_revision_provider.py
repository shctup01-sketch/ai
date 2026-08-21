"""DevelopmentRevisionPlan을 만드는 제공자 공통 인터페이스.

ScreenObservationProvider(screen_observation_provider.py)와 동일한
패턴 - 구체적인 AI 구현(OpenAI 등)을 이 추상 클래스 뒤에 감춰, 실행
계층(development_revision_executor.py)/UI가 특정 AI 제공자에 직접
의존하지 않게 한다.
"""

from abc import ABC, abstractmethod

from .development_revision_plan import DevelopmentRevisionPlan
from .development_revision_request import DevelopmentRevisionRequest


class DevelopmentRevisionProvider(ABC):
    @abstractmethod
    def plan_revision(self, request: DevelopmentRevisionRequest) -> DevelopmentRevisionPlan:
        raise NotImplementedError
