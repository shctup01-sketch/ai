"""OpenAI Responses API(Structured Outputs)로 검색 결과를 분석하는 Reviewer 구현.

OpenAI client는 생성자에서 외부 주입받는다 - 이 파일 안에서 OpenAI()를
생성하거나 API Key/환경변수/.env를 직접 다루지 않는다. Brain/Developer/
WebSearch용 Provider와는 완전히 독립적이며, 그 파일들을 수정하지 않고도
동작한다.

Reviewer는 이미 수행된 검색 결과를 검토만 하므로(직접 검색하지 않음)
Developer Provider처럼 도구 호출(tool calling) 왕복 루프가 필요 없다 -
client.responses.parse() 한 번만 호출한다.
"""

from typing import Any

from openai import (
    APIConnectionError,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)

from .research_review_request import ResearchReviewRequest
from .research_review_result import ResearchReviewResult
from .research_review_instructions import RESEARCH_REVIEW_INSTRUCTIONS
from .research_reviewer_provider import ResearchReviewerProvider

# 이 프로젝트의 다른 Provider들과 동일한 자리표시자 모델명 표기 관례를
# 따른다. 다른 Provider의 DEFAULT_MODEL을 import하지 않는다 - 이 Provider는
# 완전히 독립적으로 존재해야 한다.
DEFAULT_MODEL = "gpt-5.6-terra"

# 검색 결과 한 건의 발췌문(snippet)이 지나치게 길어 요청이 비대해지는
# 것을 막기 위한 상한. 결과 "건수"는 절대 줄이지 않고, 각 건의 snippet
# 텍스트 길이만 제한한다.
_MAX_SNIPPET_LEN = 500


class OpenAIResearchReviewerProvider(ResearchReviewerProvider):
    """client.responses.parse()로 검색 결과를 분석해 ResearchReviewResult를 만든다."""

    def __init__(self, client: Any, model: str = DEFAULT_MODEL):
        self._client = client
        self._model = model

    def review(self, request: ResearchReviewRequest) -> ResearchReviewResult:
        prompt = _build_review_prompt(request)

        try:
            response = self._client.responses.parse(
                model=self._model,
                instructions=RESEARCH_REVIEW_INSTRUCTIONS,
                input=prompt,
                text_format=ResearchReviewResult,
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
            raise RuntimeError("Reviewer의 응답을 이해하지 못했습니다. 다시 시도해주세요.")

        return response.output_parsed


def _build_review_prompt(request: ResearchReviewRequest) -> str:
    """검색 결과 "건수"는 하나도 빠짐없이 프롬프트에 포함하되, 건별 발췌문
    길이만 제한한다(API Key 등 민감정보가 여기 섞일 경로 자체가 없다 -
    ResearchReviewRequest에는 그런 필드가 없다).

    48단계 - dependency_context(이전 analysis 결과, 기본값 "")가 있으면
    마지막에 그대로 덧붙인다.

    49단계 §4 - dependency_context가 있을 때만(Analysis -> Analysis
    체인) "직접 조사 자료"/"이전 분석 결과"를 명확히 구분하는 요약
    줄과, search_results가 0건이면 그 사실이 "근거가 없다"는 뜻이
    아니라는 안내 문장을 추가한다. dependency_context가 없는 기존
    Research -> Analysis 경로(§12 A)는 이 분기를 전혀 타지 않으므로
    프롬프트가 48단계 이전과 완전히 동일하다(하위 호환).

    52단계 §9 - dependency_context에 development 모양(DeveloperResult)
    dependency도 섞일 수 있게 되면서(analysis_executor.py 참고),
    무조건 "이전 분석 결과: 있음"이라고만 적으면 실제로는 development
    dependency만 있는 경우 부정확한 문구가 된다. analysis_executor.py가
    각 dependency 앞에 붙이는 헤더("[이전 분석: ...]" / "[이전 개발
    결과: ...]")로 실제 어떤 종류가 섞여 있는지만 구분해(§7 - 새 구조화
    필드를 추가하지 않고 기존 dependency_context 문자열 안의 관례를
    그대로 재사용) 정확한 문구만 보여준다.

    54단계 §10 - development dependency가 있으면 마지막에 짧은 지시
    문단을 덧붙인다. 실기에서 Development evidence(52/54단계로 이미
    전달되고 있음에도) Analysis가 "검증할 수 없음"으로 판단해 이미
    구현된 기능을 처음부터 다시 만들자고 제안한 문제가 확인됐다 - 이미
    확인된 증거는 유효한 근거로 쓰고, 확인 안 된 것만 "검증 필요"로
    구분하며, 중복 개발을 제안하지 말라고 명시한다. AI에게 사실을
    강제로 긍정하게 하지 않는다(§10 단서) - "확인되지 않은 항목만 검증
    필요로 구분하라"는 문장이 이 균형을 유지한다.
    """
    lines = [
        f"조사 제목: {request.task_title}",
        f"조사 목표: {request.task_goal}",
        f"검색어: {request.query}",
        "",
    ]

    has_dependency_context = bool(request.dependency_context)
    has_analysis_dependency = "[이전 분석:" in request.dependency_context
    has_development_dependency = "[이전 개발 결과:" in request.dependency_context

    if has_dependency_context:
        lines.append(f"직접 조사 자료: {len(request.search_results)}건" if request.search_results else "직접 조사 자료: 없음")
        if has_analysis_dependency:
            lines.append("이전 분석 결과: 있음")
        if has_development_dependency:
            lines.append("이전 개발 결과: 있음")
        lines.append("")

    if request.search_results:
        lines.append(f"검색 결과 ({len(request.search_results)}건):")
        for idx, item in enumerate(request.search_results, start=1):
            title = item.get("title", "")
            url = item.get("url", "")
            snippet = item.get("snippet", "")
            if len(snippet) > _MAX_SNIPPET_LEN:
                snippet = snippet[:_MAX_SNIPPET_LEN] + "..."
            lines.append(f"{idx}. {title}\n   URL: {url}\n   내용: {snippet}")
    elif has_dependency_context:
        # 49단계 §4 - "검색 결과가 0건입니다"라고만 보이면 AI가 "근거
        # 전체가 없다"고 오해할 위험이 있었다(실제 재현된 문제). 원시
        # 검색 결과가 없을 뿐 이전 단계 결과라는 유효한 근거가 있다는
        # 사실을 명확한 문장으로 알린다. 52단계 - development만 있는
        # 경우도 "분석"이라고 잘못 부르지 않는다(§9).
        if has_development_dependency and has_analysis_dependency:
            prior_label = "이전 분석/개발 단계의 결과"
        elif has_development_dependency:
            prior_label = "이전 개발 단계의 결과"
        else:
            prior_label = "이전 분석 단계의 검토 결과"
        lines.append(
            f"이 단계에 직접 연결된 원시 검색 결과는 없습니다. "
            f"대신 {prior_label}가 아래에 제공됩니다. "
            "이전 결과를 유효한 입력 근거로 사용하세요."
        )
    else:
        lines.append("검색 결과 (0건):")
        lines.append("(검색 결과 없음)")

    if has_dependency_context:
        lines.append("")
        if has_development_dependency and has_analysis_dependency:
            lines.append("이전 분석/개발 결과:")
        elif has_development_dependency:
            lines.append("이전 개발 결과:")
        else:
            lines.append("이전 분석 결과:")
        lines.append(request.dependency_context)

    if has_development_dependency:
        # 54단계 §10 - "자료 없음" 오판 방지. Development evidence(산출물/
        # 실행 검증/화면 검수/수정 이력)가 제공됐는데도 이미 확인된
        # 기능을 "미구현"으로 보고 처음부터 다시 만들자고 제안하는
        # 문제가 실기에서 확인됐다(GameBlock 재개 사례). 사실을 강제로
        # 긍정하게 하지 않는다 - 확인되지 않은 항목은 "검증 필요"로
        # 남기라는 지시도 함께 준다(§10 마지막 문장).
        lines.append("")
        lines.append(
            "제공된 개발 산출물/실행 검증/검수 증거는 유효한 이전 단계 근거로 사용하세요. "
            "증거로 확인된 기능을 미구현으로 가정하지 마세요. "
            "확인되지 않은 항목만 검증 필요로 구분하세요. "
            "기존 구현과 중복되는 다음 개발을 제안하지 말고, "
            "다음 개발은 확인된 현재 상태에서의 다음 증분이어야 합니다."
        )

    return "\n".join(lines)
