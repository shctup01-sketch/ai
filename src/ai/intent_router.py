"""사용자 원문 메시지만 보고 판단하는 순수 Research 의도 라우터.

Brain(LLM)이 스스로 내리는 task_type 분류가 15-1/16단계에서 프롬프트
강화와 BrainResponse 필드 순서/스키마 수정만으로는 실기에서 세 번째로
실패했다. 이 파일은 LLM 판단을 대체하지 않고, "명백한 조사 요청인데
Brain이 general/development로 새는" 상황에 대한 최후 안전망 역할만
한다.

판정 방식은 단일 키워드("크몽" 등) 매칭이 아니라, "제작 동사 + 대상
명사" 조합(development)과 "조사 동사" 패턴(research)의 조합으로
판단한다. "웹 검색 프로그램 만들어줘"처럼 조사 관련 단어가 프로그램의
기능/용도로 명사 형태(예: "검색 프로그램")로만 쓰이면 뒤에 붙는 동사
활용형("검색해")이 없어 research로 오판되지 않는다. 애매하면
"unknown"을 반환해 general 여부까지 이 파일이 대신 판정하지 않고
Brain의 판단에 맡긴다.

이 파일은 순수 문자열 판정 로직만 제공한다 - OpenAI 호출, 웹 요청
(requests), subprocess/shell 실행, 파일 접근을 하지 않는다.
"""

from typing import Literal

from .brain_response import BrainResponse

Intent = Literal["research", "development", "unknown"]

# 조사를 "지금 수행해달라"는 동사 활용형만 매칭한다(어간+어미 결합형).
# 명사로만 쓰인 "검색 프로그램", "조사 프로그램" 등은 여기에 걸리지 않는다.
_RESEARCH_VERB_STEMS = ("조사해", "찾아봐", "찾아줘", "확인해", "검색해")

# "만들어줘/제작해줘/개발해줘"류 제작 요청 동사 어간.
_CREATION_VERB_STEMS = ("만들", "제작", "개발")

# 제작 대상이 프로그램/게임/앱/도구류일 때만 development로 판단한다
# (동사만으로는 부족 - "무엇을" 만드는지도 함께 봐야 오판을 줄인다).
_CREATION_NOUNS = ("프로그램", "게임", "앱", "어플", "애플리케이션", "도구", "툴")

CORRECTED_REPLY_TO_USER = (
    "조사 작업을 준비했습니다. 오른쪽의 '작업 실행' 버튼을 눌러 실제 검색을 시작해 주세요."
)

_MAX_TITLE_LEN = 40


def _has_research_request(text: str) -> bool:
    return any(stem in text for stem in _RESEARCH_VERB_STEMS)


def _has_creation_request(text: str) -> bool:
    has_verb = any(stem in text for stem in _CREATION_VERB_STEMS)
    has_noun = any(noun in text for noun in _CREATION_NOUNS)
    return has_verb and has_noun


def classify_intent(user_message: str) -> Intent:
    """사용자 원문 메시지 하나만 보고 명백한 의도만 판정한다.

    "제작 동사 + 대상 명사"와 "조사 동사"가 함께 나타나는 복합 요청
    (예: "크몽에서 조사해서 어떤 프로그램을 만들지 추천해줘")은 아직
    research -> development 자동 연결 기능이 없으므로 research를
    우선한다(먼저 조사부터 수행).
    """
    text = (user_message or "").strip()
    if not text:
        return "unknown"

    has_research = _has_research_request(text)
    has_creation = _has_creation_request(text)

    if has_research:
        return "research"
    if has_creation:
        return "development"
    return "unknown"


def _build_research_title(user_message: str) -> str:
    trimmed = user_message.strip()
    if len(trimmed) > _MAX_TITLE_LEN:
        trimmed = trimmed[:_MAX_TITLE_LEN] + "..."
    return f"웹 정보 조사: {trimmed}"


def build_corrected_research_response(user_message: str, original: BrainResponse) -> BrainResponse:
    """Brain이 명백한 조사 요청을 놓쳤을 때 쓸 최소한의 Research용 응답을 만든다.

    LLM을 다시 호출하지 않고 결정적으로만 구성한다 - research_title은
    사용자 메시지를 정해진 길이로 잘라 만들고, research_goal은 사용자
    원문을 그대로 사용한다. 조사 결과 자체는 여기서 만들지 않는다
    (실제 조사는 ResearchWorker/WebSearchTool이 수행한다).
    """
    return BrainResponse(
        task_type="research",
        is_dev_request=False,
        needs_more_info=False,
        plan_ready=True,
        reply_to_user=CORRECTED_REPLY_TO_USER,
        project_name=None,
        requirements_summary=None,
        feature_list=None,
        task_steps=None,
        research_title=_build_research_title(user_message),
        research_goal=user_message.strip(),
    )
