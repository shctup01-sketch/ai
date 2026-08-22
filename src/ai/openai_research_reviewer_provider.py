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

    48단계 - dependency_context(이전 analysis 결과 요약, 기본값 "")가
    있으면 마지막에 그대로 덧붙인다. 기본값이 빈 문자열이라 이 필드를
    쓰지 않는 기존 호출(Research -> Analysis만 있는 경우)은 프롬프트가
    한 글자도 바뀌지 않는다.
    """
    lines = [
        f"조사 제목: {request.task_title}",
        f"조사 목표: {request.task_goal}",
        f"검색어: {request.query}",
        "",
        f"검색 결과 ({len(request.search_results)}건):",
    ]

    if not request.search_results:
        lines.append("(검색 결과 없음)")
    else:
        for idx, item in enumerate(request.search_results, start=1):
            title = item.get("title", "")
            url = item.get("url", "")
            snippet = item.get("snippet", "")
            if len(snippet) > _MAX_SNIPPET_LEN:
                snippet = snippet[:_MAX_SNIPPET_LEN] + "..."
            lines.append(f"{idx}. {title}\n   URL: {url}\n   내용: {snippet}")

    if request.dependency_context:
        lines.append("")
        lines.append("이전 분석 결과:")
        lines.append(request.dependency_context)

    return "\n".join(lines)
