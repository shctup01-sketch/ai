import os

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from .brain_instructions import BRAIN_INSTRUCTIONS
from .brain_response import BrainResponse
from .provider import AIProvider

load_dotenv()

DEFAULT_MODEL = "gpt-5.6-terra"


class OpenAIProvider(AIProvider):
    """OpenAI Responses API(Structured Outputs)를 사용하는 Provider 구현."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    def send_message(self, messages: list[dict]) -> BrainResponse:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI API Key가 설정되지 않았습니다. "
                "프로젝트 루트의 .env 파일에 OPENAI_API_KEY 값을 입력한 뒤 다시 시도해주세요."
            )

        client = OpenAI(api_key=api_key)

        try:
            response = client.responses.parse(
                model=self._model,
                instructions=BRAIN_INSTRUCTIONS,
                input=messages,
                text_format=BrainResponse,
            )
        except AuthenticationError as exc:
            raise RuntimeError(
                "OpenAI API Key가 올바르지 않습니다. .env 파일의 값을 확인해주세요."
            ) from exc
        except RateLimitError as exc:
            raise RuntimeError(
                "OpenAI 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            ) from exc
        except APIConnectionError as exc:
            raise RuntimeError(
                "인터넷 연결을 확인해주세요. OpenAI 서버에 연결할 수 없습니다."
            ) from exc
        except OpenAIError as exc:
            raise RuntimeError(
                "OpenAI API 호출 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요."
            ) from exc

        if response.output_parsed is None:
            raise RuntimeError("Brain의 응답을 이해하지 못했습니다. 다시 시도해주세요.")

        return response.output_parsed
