import logging
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
from .intent_router import build_corrected_research_response, classify_intent
from .provider import AIProvider

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5.6-terra"


def _extract_last_user_message(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content", ""))
    return ""


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

        parsed = response.output_parsed

        # Brain 자체 분류(task_type)가 15-1/16단계 수정 이후에도 실기에서
        # 반복적으로 새는 것이 확인되어, 사용자 원문만 보는 순수 규칙 기반
        # IntentRouter로 명백한 research 요청을 놓치지 않는지 마지막으로
        # 한 번 더 확인한다. IntentRouter가 "research"라고 판단했는데
        # Brain 응답이 research+plan_ready 조합이 아니면, Brain의 (조사
        # 결과를 흉내 낸) 긴 답변을 그대로 쓰지 않고 결정적으로 만든
        # 최소한의 Research용 응답으로 교정한다. IntentRouter가
        # "development"나 "unknown"이면 Brain의 판단을 그대로 존중한다.
        last_user_message = _extract_last_user_message(messages)
        router_intent = classify_intent(last_user_message)

        final_response = parsed
        if router_intent == "research" and (
            parsed.task_type != "research" or not parsed.plan_ready
        ):
            final_response = build_corrected_research_response(last_user_message, parsed)

        # 실기 분류 오류를 재현 없이 진단하기 위한 개발용 로그. API Key/
        # 시스템 지시문/사용자 원문 등 민감한 내용은 남기지 않는다 -
        # 분류 결과(enum 값)만 기록한다.
        logger.debug(
            "Intent router: %s | Brain classification: %s | Final classification: %s",
            router_intent,
            parsed.task_type,
            final_response.task_type,
        )
        logger.debug(
            "Final response fields: task_type=%s is_dev_request=%s "
            "needs_more_info=%s plan_ready=%s",
            final_response.task_type,
            final_response.is_dev_request,
            final_response.needs_more_info,
            final_response.plan_ready,
        )
        return final_response
