"""OpenAI Responses API(Structured Outputs)로 ChiefBrainPlan을 만드는 구현.

기존 OpenAIProvider(openai_provider.py, 지금의 Brain)와 동일하게 이
파일 안에서 OPENAI_API_KEY를 직접 읽고 OpenAI() client를 직접 생성한다
- WebSearch/Reviewer용 Provider(client 외부 주입)와는 다른 계열이다.
Chief Brain은 Brain과 같은 "최상위에서 직접 사용자와 대화하는 주체"
역할이라, 그 자리에서 이미 확립된 openai_provider.py의 패턴(자체 API
Key 읽기 + 자체 client 생성 + 동일한 예외 변환)을 그대로 따른다.

Developer/Brain/WebSearch/Reviewer 등 이 프로젝트의 다른 어떤 Provider와도
DEFAULT_MODEL을 공유하지 않는다(자체 상수) - 이 프로젝트에는 현재
"gpt-5.6-terra"라는 자리표시자 모델명 하나만 실제로 쓰이고 있고, 다른
이름의 "더 강력한" 모델이 이미 코드/SDK 어딘가에 확인된 적은 없다.
그래서 임의로 새 모델 이름을 지어내는 대신, 같은 값을 쓰되 Developer용
설정과 독립적으로 바꿀 수 있는 구조(별도 상수 + 생성자 매개변수)만
만들어 둔다 - 실제로 더 강한 모델 이름이 정해지면 이 상수 하나만
바꾸면 된다.
"""

import os

from openai import (
    APIConnectionError,
    AuthenticationError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from .chief_brain_instructions import CHIEF_BRAIN_INSTRUCTIONS
from .chief_brain_plan import ChiefBrainPlan, validate_chief_brain_plan
from .chief_brain_provider import ChiefBrainProvider

DEFAULT_MODEL = "gpt-5.6-terra"


class ChiefBrainPlanError(Exception):
    """Chief Brain이 만든 계획이 최소한의 구조적 정합성 검사를 통과하지 못했을 때 발생한다."""


class OpenAIChiefBrainProvider(ChiefBrainProvider):
    """client.responses.parse()로 ChiefBrainPlan을 만들고 최소한의 구조 검증을 거친다."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    def plan_work(self, messages: list[dict]) -> ChiefBrainPlan:
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
                instructions=CHIEF_BRAIN_INSTRUCTIONS,
                input=messages,
                text_format=ChiefBrainPlan,
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
            raise RuntimeError("Chief Brain의 응답을 이해하지 못했습니다. 다시 시도해주세요.")

        plan = response.output_parsed

        errors = validate_chief_brain_plan(plan)
        if errors:
            raise ChiefBrainPlanError(
                "Chief Brain이 만든 계획이 구조 검증을 통과하지 못했습니다: " + "; ".join(errors)
            )

        return plan
