"""ScreenObservationResult를 만드는 제공자 공통 인터페이스.

ResearchReviewerProvider(research_reviewer_provider.py)와 동일한 패턴 -
구체적인 AI 구현(OpenAI 등)을 이 추상 클래스 뒤에 감춰, 실행 계층
(screen_observation_executor.py)/UI가 특정 AI 제공자에 직접 의존하지
않게 한다.
"""

from abc import ABC, abstractmethod

from .screen_observation_request import ScreenObservationRequest
from .screen_observation_result import ScreenObservationResult


class ScreenObservationProvider(ABC):
    @abstractmethod
    def observe(self, request: ScreenObservationRequest) -> ScreenObservationResult:
        raise NotImplementedError
