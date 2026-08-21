"""OpenAI Responses API(Structured Outputs)로 DevelopmentRevisionPlan을 만드는 구현.

OpenAIScreenObservationProvider(openai_screen_observation_provider.py)와
동일한 client 생성/예외 변환 패턴을 그대로 재사용한다 - 이 파일 안에서
OPENAI_API_KEY를 직접 읽고 OpenAI() client를 직접 생성한다.

기존 OpenAIChiefBrainProvider를 재사용하지 않고 별도 Provider를 둔
이유는 openai_screen_observation_provider.py가 이미 남긴 설명과 같다:
OpenAIChiefBrainProvider는 ChiefBrainProvider(ABC).plan_work() 계약에
묶여 있고, 그 계약은 client.responses.parse(text_format=ChiefBrainPlan)
으로 고정돼 있다. DevelopmentRevisionPlan(judgment/impact_summary/
steps)은 ChiefBrainPlan(needs_more_info/ready/objective/execution_mode/
steps/clarification_question/user_reply)과 구조가 다르고, 애초에 이
좁은 revision 판단에 project 전체 계획 계약을 억지로 재사용하면
38단계 §7이 명시적으로 금지한 "revision을 새 project 전체 plan으로
취급"하는 상황이 그대로 재현된다. 새 Vision/Tool 프로토콜은 전혀
쓰지 않는다(텍스트 입력만, image_content.py 관여 없음).
"""

import os

from openai import (
    APIConnectionError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from .development_revision_instructions import DEVELOPMENT_REVISION_INSTRUCTIONS
from .development_revision_plan import DevelopmentRevisionPlan
from .development_revision_provider import DevelopmentRevisionProvider
from .development_revision_request import DevelopmentRevisionRequest

DEFAULT_MODEL = "gpt-5.6-terra"


class OpenAIDevelopmentRevisionProvider(DevelopmentRevisionProvider):
    """client.responses.parse()로 수정 요청을 판단해 DevelopmentRevisionPlan을 만든다."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    def plan_revision(self, request: DevelopmentRevisionRequest) -> DevelopmentRevisionPlan:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI API Key가 설정되지 않았습니다. "
                "프로젝트 루트의 .env 파일에 OPENAI_API_KEY 값을 입력한 뒤 다시 시도해주세요."
            )

        client = OpenAI(api_key=api_key)
        messages = [{"role": "user", "content": _build_prompt(request)}]

        try:
            response = client.responses.parse(
                model=self._model,
                instructions=DEVELOPMENT_REVISION_INSTRUCTIONS,
                input=messages,
                text_format=DevelopmentRevisionPlan,
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
            raise RuntimeError("수정 계획을 이해하지 못했습니다. 다시 시도해주세요.")

        return response.output_parsed


def _build_prompt(request: DevelopmentRevisionRequest) -> str:
    created_text = ", ".join(request.created_files) if request.created_files else "(없음)"
    modified_text = ", ".join(request.modified_files) if request.modified_files else "(없음)"
    screen_text = request.screen_observation_summary or "(화면 확인을 하지 않았습니다)"
    return (
        f"프로젝트 목표: {request.project_objective}\n\n"
        f"방금 완료된 단계: {request.current_step_title}\n"
        f"그 단계의 목표: {request.current_step_goal}\n"
        f"실제로 만들어진 것: {request.developer_summary}\n"
        f"생성된 파일: {created_text}\n"
        f"수정된 파일: {modified_text}\n\n"
        f"화면 분석 요약: {screen_text}\n\n"
        f"사용자의 수정 요청:\n{request.user_revision_request}"
    )
