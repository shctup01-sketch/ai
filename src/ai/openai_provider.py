from .provider import AIProvider


class OpenAIProvider(AIProvider):
    """OpenAI 연결 뼈대. 실제 API 호출 없이 테스트 응답만 반환한다."""

    def send_message(self, messages: list[dict]) -> str:
        return "OpenAIProvider 연결 준비가 완료되었습니다."
