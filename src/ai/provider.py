from abc import ABC, abstractmethod

from .brain_response import BrainResponse


class AIProvider(ABC):
    """AI 제공자 공통 인터페이스: 메시지 목록을 주면 구조화된 Brain 응답을 돌려준다."""

    @abstractmethod
    def send_message(self, messages: list[dict]) -> BrainResponse:
        raise NotImplementedError
