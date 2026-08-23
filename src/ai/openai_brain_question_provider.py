"""OpenAI Responses API(Structured Outputs)로 Brain 질문에 답하는 구현.

openai_chief_brain_provider.py와 동일한 패턴(자체 API Key 읽기 + 자체
client 생성 + 동일한 예외 변환)을 그대로 따른다 - 새 예외 처리 방식을
만들지 않는다. DEFAULT_MODEL도 새로 짓지 않고 openai_chief_brain_provider의
값을 그대로 가져와 쓴다(58단계 - "이 프로젝트에 실제로 쓰이는 모델
이름은 하나뿐"이라는 그 파일의 기존 설명을 그대로 따른다. Chief Brain과
독립적으로 모델을 바꿀 수 있도록 생성자 인자는 별도로 둔다).

58단계 §9 - client.responses.parse()가 돌려주는 Response 객체에
usage(input_tokens/output_tokens/total_tokens)가 이미 포함되어 있음을
SDK 소스(openai.types.responses.response.Response/ResponseUsage)로
직접 확인했다. 이번 단계에서 비용 대시보드를 새로 만들지는 않지만,
향후 단계가 바로 쓸 수 있도록 이 응답에서 usage만 뽑아 last_usage에
저장해 둔다(새 저장소/새 AI 호출 없음 - 이미 오는 응답을 읽기만 한다).
"""

import os

from openai import (
    APIConnectionError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from .brain_question_answer import BrainQuestionAnswer
from .brain_question_instructions import BRAIN_QUESTION_INSTRUCTIONS
from .brain_question_provider import BrainQuestionProvider
from .brain_question_request import BrainQuestionRequest
from .openai_chief_brain_provider import DEFAULT_MODEL


def extract_usage_info(response: object) -> dict | None:
    """§9 - Response.usage가 있으면 input/output/total token 수만 뽑는다.

    usage 자체가 없거나(None) 예상 필드가 없으면 지어내지 않고 None을
    돌려준다 - 존재가 확인된 값만 사용한다.
    """
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    total_tokens = getattr(usage, "total_tokens", None)
    if input_tokens is None and output_tokens is None and total_tokens is None:
        return None
    return {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": total_tokens}


class OpenAIBrainQuestionProvider(BrainQuestionProvider):
    """client.responses.parse()로 BrainQuestionAnswer를 만든다."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model
        self.last_usage: dict | None = None

    def answer(self, request: BrainQuestionRequest) -> BrainQuestionAnswer:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI API Key가 설정되지 않았습니다. "
                "프로젝트 루트의 .env 파일에 OPENAI_API_KEY 값을 입력한 뒤 다시 시도해주세요."
            )

        client = OpenAI(api_key=api_key)

        prompt = f"프로젝트 상황:\n{request.project_context}\n\n사용자 질문:\n{request.question}"

        try:
            response = client.responses.parse(
                model=self._model,
                instructions=BRAIN_QUESTION_INSTRUCTIONS,
                input=[{"role": "user", "content": prompt}],
                text_format=BrainQuestionAnswer,
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
            raise RuntimeError("Brain의 답변을 이해하지 못했습니다. 다시 시도해주세요.")

        self.last_usage = extract_usage_info(response)

        return response.output_parsed
