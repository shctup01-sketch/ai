from abc import ABC, abstractmethod


class AIProvider(ABC):
    """AI 제공자 공통 인터페이스: 메시지 목록을 주면 응답 문자열을 돌려준다."""

    @abstractmethod
    def send_message(self, messages: list[dict]) -> str:
        raise NotImplementedError
