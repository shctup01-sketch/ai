"""OpenAI Responses API(Structured Outputs + Vision)로 ScreenObservationResult를 만드는 구현.

OpenAIChiefBrainProvider(openai_chief_brain_provider.py)와 동일하게 이
파일 안에서 OPENAI_API_KEY를 직접 읽고 OpenAI() client를 직접 생성한다 -
이 화면 관찰 기능은 MainWindow가 다른 서비스의 client를 전달받지 않고
직접 호출하는 최상위 기능이라, ChiefBrainService와 같은 방식(자체 API
Key 읽기 + 자체 client 생성 + 동일한 예외 변환)을 따른다.

새 Vision 프로토콜을 만들지 않는다 - image_content.py가 26단계에서 이미
SDK 타입 정의로 확인한 input_image content item
({"type": "input_image", "image_url": "data:...", "detail": "auto"})을
그대로 재사용한다.

기존 OpenAIChiefBrainProvider를 재사용하지 않고 별도 Provider를 둔
이유(9단계 "새 Provider 남발 금지"에 대한 답): OpenAIChiefBrainProvider는
ChiefBrainProvider(ABC).plan_work() 계약에 묶여 있고, 이 계약은
client.responses.parse(text_format=ChiefBrainPlan)으로 고정되어 있다.
화면 관찰 결과(summary/observations/issues/next_action)는
ChiefBrainPlan(needs_more_info/ready/objective/steps/
clarification_question/user_reply)과 구조가 다르므로, 그 계약을 억지로
재사용하면 "ChiefBrainPlan을 화면 분석 결과 모델로 쓰지 말라"는 이번
단계 지침을 정면으로 어기게 된다. 대신 client 생성 패턴/예외 변환
로직/image_content.py의 이미지 입력 형식은 전부 동일하게 재사용해
중복을 최소화했다.
"""

import os

from openai import (
    APIConnectionError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from .image_content import build_input_image_item, build_input_text_item
from .screen_observation_instructions import SCREEN_OBSERVATION_INSTRUCTIONS
from .screen_observation_provider import ScreenObservationProvider
from .screen_observation_request import ScreenObservationRequest
from .screen_observation_result import ScreenObservationResult

DEFAULT_MODEL = "gpt-5.6-terra"


class OpenAIScreenObservationProvider(ScreenObservationProvider):
    """client.responses.parse()로 화면 이미지를 분석해 ScreenObservationResult를 만든다."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    def observe(self, request: ScreenObservationRequest) -> ScreenObservationResult:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI API Key가 설정되지 않았습니다. "
                "프로젝트 루트의 .env 파일에 OPENAI_API_KEY 값을 입력한 뒤 다시 시도해주세요."
            )

        client = OpenAI(api_key=api_key)
        messages = [{"role": "user", "content": _build_content(request)}]

        try:
            response = client.responses.parse(
                model=self._model,
                instructions=SCREEN_OBSERVATION_INSTRUCTIONS,
                input=messages,
                text_format=ScreenObservationResult,
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
            raise RuntimeError("화면 관찰 결과를 이해하지 못했습니다. 다시 시도해주세요.")

        return response.output_parsed


def _build_content(request: ScreenObservationRequest) -> list[dict]:
    text = (
        f"전체 목표: {request.objective}\n"
        f"이번 화면 확인 목적: {request.step_goal}\n"
        f"승인 사유: {request.approval_reason}"
    )
    return [build_input_text_item(text), build_input_image_item(request.image_data_url)]
