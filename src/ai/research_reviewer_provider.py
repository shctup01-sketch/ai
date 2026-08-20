"""ResearchReviewer의 추상 인터페이스.

WebSearchProvider와 동일한 패턴 - 구체적인 AI 구현(OpenAI 등)을 이
추상 클래스 뒤에 감춰, ResearchReviewService/MainWindow가 특정 AI
제공자에 직접 의존하지 않게 한다.
"""

from abc import ABC, abstractmethod

from .research_review_request import ResearchReviewRequest
from .research_review_result import ResearchReviewResult


class ResearchReviewerProvider(ABC):
    @abstractmethod
    def review(self, request: ResearchReviewRequest) -> ResearchReviewResult:
        raise NotImplementedError
