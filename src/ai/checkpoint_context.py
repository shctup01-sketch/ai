"""project checkpoint 승인 Dialog 등에서 이전 step 결과를 사람이 읽을
수 있는 텍스트로 보여주기 위한 순수 규칙 기반 헬퍼(42단계).

새 AI 요약/비교 호출을 하지 않는다(§4/§6/§15) - 이미 있는 결과 객체
(ResearchReviewResult/DeveloperResult/ScreenObservationResult는 모두
"summary" 필드를 갖고 있다 - 각 모델 정의 참고)의 summary 필드를
우선 쓰고, research task의 결과(순수 dict - research_worker.py 참고,
필드: task_type/title/goal/query/search_results)는 title/goal/query/
search_results만 규칙 기반으로 뽑는다(기존 _show_research_result_popup의
표시 방식과 같은 형식을 재사용한다). 없는 필드를 지어내지 않는다.

50단계 - build_development_execution_spec()은 Development checkpoint
승인 직전에 "이번 개발에서 무엇이 만들어지는지"를 보여주는 실행
명세를 만든다. 여기서도 새 AI 호출/새 Provider가 없다(§2/§18) -
BrainTaskStep.goal(항상 존재하는 필드)과 최근 ResearchReviewResult의
실제 필드(recommended_idea/recommendation_reason/next_action/summary/
risks - research_review_result.py 정의 그대로, candidate_ideas/
market_observations는 §10의 활용 우선순위에 없어 쓰지 않는다)만 텍스트
분할/키워드 매칭으로 재배열한다. 없는 정보(예: 제외 범위를 알려주는
문장이 실제로 없음)는 각 절마다 명확한 "정보 없음"류 문장으로
표시한다(§5/§9) - 있지도 않은 제외 항목/관계/완료 기준을 새로
지어내지 않는다.
"""

import re

from pydantic import BaseModel

from .brain_task_step import BrainTaskStep
from .chief_brain_plan import ChiefBrainPlan
from .orchestration_step_result import OrchestrationStepResult
from .project_product_context import ProjectProductContext, describe_product_context
from .research_review_result import ResearchReviewResult


def find_latest_step_result(
    completed_steps: list[OrchestrationStepResult], task_type: str
) -> OrchestrationStepResult | None:
    """completed_steps를 뒤에서부터 훑어 task_type이 일치하는 가장 최근
    "completed" 결과 하나만 돌려준다(§5 - 전체 프로젝트 기록을 전부
    표시하지 않는다, 필요하면 각각 1개씩만 우선 표시한다).
    """
    for entry in reversed(completed_steps):
        if entry.task_type == task_type and entry.status == "completed":
            return entry
    return None


def describe_step_result(entry: OrchestrationStepResult) -> str:
    """entry.result에서 사람이 읽을 수 있는 텍스트를 규칙 기반으로 뽑는다.

    result가 summary 필드를 가진 pydantic 모델이면(analysis/development/
    screen_observation 결과가 모두 여기 해당한다) 그 필드를 그대로 쓴다
    (§6 - summary 같은 사용자 표시용 필드를 우선 사용). research task의
    결과는 summary 필드가 없는 순수 dict라 title/goal/query/
    search_results만 뽑는다. 어느 쪽에도 해당하지 않으면(알 수 없는
    형태) 내부 객체 repr을 그대로 보여주지 않고 "결과 없음"으로
    안전하게 처리한다.
    """
    result = entry.result

    if isinstance(result, BaseModel):
        summary = getattr(result, "summary", None)
        return summary if summary else "결과 없음"

    if isinstance(result, dict):
        parts = []
        title = result.get("title")
        goal = result.get("goal")
        query = result.get("query")
        if title:
            parts.append(f"제목: {title}")
        if goal:
            parts.append(f"목표: {goal}")
        if query:
            parts.append(f"검색어: {query}")

        search_results = result.get("search_results")
        if isinstance(search_results, list) and search_results:
            items_text = "\n".join(
                f"  - {item.get('title', '')}\n    {item.get('url', '')}"
                for item in search_results
                if isinstance(item, dict)
            )
            parts.append(f"검색 결과 {len(search_results)}건:\n{items_text}")

        return "\n".join(parts) if parts else "결과 없음"

    return "결과 없음"


# 50단계 - Development 실행 명세(build_development_execution_spec) 전용
# 설정. GameBlock 등 특정 프로젝트 전용 keyword는 전혀 두지 않는다(§7 -
# 범용적으로 "핵심 관계/연결" 절만 만들고, 실제 project 데이터에서
# 추출한다). 각 절의 항목 수를 제한해 장기 프로젝트에서 UI가 지나치게
# 길어지지 않게 한다(§13).
_MAX_ITEMS_PER_SECTION = 6
_EXCLUSION_KEYWORDS = ("제외", "포함하지 않", "만들지 않는다", "하지 않는다", "범위 밖", "구현하지 않는다", "다루지 않는다")
_COMPLETION_KEYWORDS = ("완료", "가능", "생성", "통과", "실행")
_RELATIONSHIP_MARKERS = ("→", "->")

_NO_EXCLUSION_TEXT = "이번 단계에서 제외되는 범위가 명시되어 있지 않습니다."
_NO_RELATIONSHIP_TEXT = "명시된 핵심 관계/연결 규칙이 없습니다."
_NO_COMPLETION_TEXT = "명시된 완료 판정 기준이 없습니다."
_NO_NEXT_STEP_TEXT = "명시된 후속 범위 없음"
_NO_BUILD_ITEMS_TEXT = "명시된 개발 범위 없음"


_ITEM_SPLIT_PATTERN = re.compile(r"[\n,、]+|(?<=[.!?])\s+")


def _split_into_items(text: str) -> list[str]:
    """자유 텍스트를 최소한의 규칙(줄바꿈/쉼표류 구분자, 마침표 뒤
    공백)으로 항목 목록으로 나눈다. 새 문장을 만들지 않는다 - 이미
    있는 텍스트를 나누고 앞의 "-"/"•"/"*" 같은 기존 불릿 기호만
    정리할 뿐이다. 줄바꿈 없이 쉼표로 나열된 목록과, 마침표로 문장이
    끝나는 서술형 텍스트가 한 goal 안에 섞여 있어도(실제 Chief Brain
    plan에서 흔함) 둘 다 항목으로 나뉘도록 구분자를 함께 쓴다.
    """
    if not text:
        return []
    parts = _ITEM_SPLIT_PATTERN.split(text.strip())

    items = []
    for part in parts:
        cleaned = part.strip().lstrip("-•* ").rstrip(".").strip()
        if cleaned:
            items.append(cleaned)
    return items


def _find_items_with_keywords(items: list[str], keywords: tuple[str, ...]) -> list[str]:
    return [item for item in items if any(keyword in item for keyword in keywords)]


def _append_spec_section(lines: list[str], title: str, items: list[str], fallback: str) -> None:
    """§13 - 항목이 너무 많으면 상한(_MAX_ITEMS_PER_SECTION)까지만 보여주고
    나머지는 "외 N건"으로만 표시한다(전체를 다 나열하지 않는다)."""
    lines.append(title)
    if not items:
        lines.append(fallback)
        lines.append("")
        return
    shown = items[:_MAX_ITEMS_PER_SECTION]
    for item in shown:
        lines.append(f"- {item}")
    remaining = len(items) - len(shown)
    if remaining > 0:
        lines.append(f"  ...(외 {remaining}건)")
    lines.append("")


def build_development_execution_spec(
    step: BrainTaskStep,
    analysis_result: ResearchReviewResult | None,
    product_context: ProjectProductContext | None = None,
) -> str:
    """50단계 - Development checkpoint 승인 직전에 보여줄 실행 명세.

    §10의 활용 우선순위(title/goal -> recommended_idea ->
    recommendation_reason -> next_action -> summary -> risks)를
    따른다. Research 원자료는 쓰지 않는다(§11 - 이미 있는 조사 결과
    표시 절과 겹치지 않게 한다). 새 AI 호출/새 Provider 없음(§2/§18).

    57단계 - product_context(프로젝트의 승인된 장기 제품 기준)가 있으면
    맨 앞에 짧게 별도 절로 보여준다. "이번 단계에서 만드는 것" 등 나머지
    절과는 분리한다 - 제품 기준은 판단 기준일 뿐, 이번 단계에서 실제로
    구현하기로 한 목록(build_items)이 아니다(§4, 목표와 증거를 섞지
    않는다).
    """
    goal_items = _split_into_items(step.goal)

    recommended_idea = analysis_result.recommended_idea if analysis_result else ""
    recommendation_reason = analysis_result.recommendation_reason if analysis_result else ""
    next_action = analysis_result.next_action if analysis_result else ""
    summary = analysis_result.summary if analysis_result else ""
    risks = analysis_result.risks if analysis_result else []

    # "만드는 것"은 goal이 기본이다 - Analysis의 recommended_idea가 goal에
    # 이미 없는 새 내용을 담고 있을 때만 덧붙인다(§10 "같은 내용을 중복
    # 표시하지 않는다"). 제외 문장(예: "전투 시스템은 만들지 않는다")이
    # goal에 섞여 있으면 "만드는 것"에서는 빼서 "제외" 절과 모순되게
    # 보이지 않게 한다 - 그 문장 자체는 아래 exclusion_items로 그대로
    # 표시된다.
    build_items = [item for item in goal_items if not any(keyword in item for keyword in _EXCLUSION_KEYWORDS)]
    if recommended_idea and recommended_idea not in step.goal:
        build_items.append(recommended_idea)

    scan_text = "\n".join(part for part in [step.goal, recommended_idea, recommendation_reason, next_action, summary, *risks] if part)
    scan_items = _split_into_items(scan_text)

    exclusion_items = _find_items_with_keywords(scan_items, _EXCLUSION_KEYWORDS)
    relationship_items = _find_items_with_keywords(scan_items, _RELATIONSHIP_MARKERS)
    completion_items = _find_items_with_keywords(scan_items, _COMPLETION_KEYWORDS)

    # §9 - 다음 단계 후보는 Analysis의 next_action을 우선하고, 없으면
    # risks를 후속 확인 대상으로 본다(risks 자체가 "다음에 확인해야 할
    # 것"과 자연스럽게 겹친다). 둘 다 없으면 정직하게 "없음"으로 표시.
    next_step_items = _split_into_items(next_action) or list(risks)

    lines: list[str] = ["--- 이번 개발 실행 명세 ---", ""]
    product_context_text = describe_product_context(product_context)
    if product_context_text:
        lines.append("[프로젝트 제품 기준(장기 방향)]")
        lines.append(product_context_text)
        lines.append("")
    _append_spec_section(lines, "이번 단계에서 만드는 것:", build_items, _NO_BUILD_ITEMS_TEXT)
    _append_spec_section(lines, "이번 단계에서 제외:", exclusion_items, _NO_EXCLUSION_TEXT)
    _append_spec_section(lines, "개발 완료 후 확인 예정:", build_items, _NO_BUILD_ITEMS_TEXT)
    _append_spec_section(lines, "핵심 관계/연결:", relationship_items, _NO_RELATIONSHIP_TEXT)
    _append_spec_section(lines, "완료 판정:", completion_items, _NO_COMPLETION_TEXT)
    _append_spec_section(lines, "다음 단계:", next_step_items, _NO_NEXT_STEP_TEXT)

    return "\n".join(lines).rstrip()


def _describe_research_compact(entry: OrchestrationStepResult) -> str:
    """58단계 - Brain 질문 문맥 전용. describe_step_result의 research
    분기는 검색 결과 각각의 title/url을 전부 나열해(체크포인트 화면
    표시용으로는 적절하지만) Brain 질문 프롬프트에 넣기엔 길다(§3 "전체
    URL 목록을 보내지 마세요"). 여기서는 제목/목표/검색어와 건수만
    남긴다 - 없는 정보를 지어내지 않고, 있는 정보를 압축할 뿐이다.
    """
    result = entry.result
    if not isinstance(result, dict):
        return describe_step_result(entry)

    parts = []
    title = result.get("title")
    goal = result.get("goal")
    query = result.get("query")
    if title:
        parts.append(f"제목: {title}")
    if goal:
        parts.append(f"목표: {goal}")
    if query:
        parts.append(f"검색어: {query}")

    search_results = result.get("search_results")
    count = len(search_results) if isinstance(search_results, list) else 0
    parts.append(f"검색 결과: {count}건")

    return "\n".join(parts) if parts else "결과 없음"


def _describe_development_evidence_compact(entry: OrchestrationStepResult) -> str:
    """58단계 - Brain 질문 문맥 전용. DeveloperResult의 summary에 더해,
    DevelopmentEvidenceSnapshot(54단계)이면 실제로 존재하는 실행 검증/
    화면 검수/수정 이력만 짧게 덧붙인다. getattr(..., 기본값)으로
    판별한다 - 순수 DeveloperResult(evidence 없음)는 이 블록에서 아무
    것도 추가되지 않는다(§7 - 없는 증거를 지어내지 않는다, analysis_
    executor.py._format_development_dependency와 동일한 판별 원칙을
    따르되, 여기서는 AI 프롬프트 dependency_context 형식이 아니라 Brain
    질문용 한두 문장 요약만 만든다).
    """
    result = entry.result
    summary = getattr(result, "summary", None) or "결과 없음"
    lines = [summary]

    if getattr(result, "runtime_checked", False):
        runtime_success = getattr(result, "runtime_success", None)
        runtime_summary = getattr(result, "runtime_summary", None)
        status_text = "성공" if runtime_success else "실패" if runtime_success is False else "확인됨"
        detail = f" - {runtime_summary}" if runtime_summary else ""
        lines.append(f"실행 검증: {status_text}{detail}")

    visual_review_summary = getattr(result, "visual_review_summary", None)
    if visual_review_summary:
        lines.append(f"화면 검수: {visual_review_summary}")

    revision_requested = getattr(result, "revision_requested", None)
    revision_summary = getattr(result, "revision_summary", None)
    if revision_requested or revision_summary:
        lines.append(f"수정 이력: 요청 - {revision_requested or '(기록 없음)'} / 결과 - {revision_summary or '(기록 없음)'}")

    return "\n".join(lines)


def build_brain_question_context(
    plan: ChiefBrainPlan,
    step: BrainTaskStep,
    approval_reason: str | None,
    completed_steps: list[OrchestrationStepResult],
    product_context: ProjectProductContext | None = None,
    project_name: str | None = None,
    last_user_request: str | None = None,
    recent_consultation: list[tuple[str, str]] | None = None,
) -> str:
    """58단계 - checkpoint에서 Brain에게 질문할 때 함께 보낼 압축된
    프로젝트 상황 요약.

    저장된 project state 전체 JSON을 그대로 보내지 않는다(§3/§4 - 토큰
    낭비 금지). 이미 있는 규칙 기반 helper(find_latest_step_result/
    describe_step_result/describe_product_context)만 재사용해 짧은
    텍스트로 만든다 - 새 AI 요약 호출이 없다. 존재하지 않는 정보는
    지어내지 않는다 - 없는 항목(product_context/research/analysis/
    development 중 없는 것)은 그 절 자체를 넣지 않는다.

    59단계(사용자 검토) - recent_consultation(기본값 None)은 같은
    checkpoint 안에서 방금 오간 (질문, 답변) 튜플의 짧은 목록이다.
    "메인 채팅에서 계속 대화"가 실제로 연속 대화가 되려면 두 번째
    질문이 첫 질문/답변을 알아야 한다 - 호출자(main_window.py)가 몇
    턴까지 유지할지(무한 누적 금지) 결정해 넘긴다. 이 함수는 받은
    목록을 그대로만 짧게 나열할 뿐, 스스로 개수를 제한하거나 저장하지
    않는다(그 책임은 호출자에게 있다 - 여기서는 순수 포맷팅만 한다).
    """
    lines: list[str] = [
        f"프로젝트 이름: {project_name or plan.objective}",
        f"사용자의 원래 목표: {plan.objective}",
    ]
    if last_user_request:
        lines.append(f"가장 최근 사용자 요청: {last_user_request}")

    product_context_text = describe_product_context(product_context)
    if product_context_text:
        lines.append("")
        lines.append("[프로젝트 제품 기준(장기 방향) - 판단 기준일 뿐 구현 증거 아님]")
        lines.append(product_context_text)

    lines.append("")
    lines.append("[지금 확인이 필요한 단계]")
    lines.append(f"이름: {step.title}")
    lines.append(f"목표: {step.goal}")
    if approval_reason:
        lines.append(f"확인이 필요한 이유: {approval_reason}")

    research_entry = find_latest_step_result(completed_steps, "research")
    if research_entry is not None:
        lines.append("")
        lines.append("[가장 최근 조사 결과 요약]")
        lines.append(_describe_research_compact(research_entry))

    analysis_entry = find_latest_step_result(completed_steps, "analysis")
    if analysis_entry is not None:
        lines.append("")
        lines.append("[가장 최근 분석 결과 요약]")
        lines.append(describe_step_result(analysis_entry))

    development_entry = find_latest_step_result(completed_steps, "development")
    if development_entry is not None:
        lines.append("")
        lines.append("[가장 최근 개발 결과 요약(실제 확인된 증거만)]")
        lines.append(_describe_development_evidence_compact(development_entry))

    if recent_consultation:
        lines.append("")
        lines.append("[이번 checkpoint에서 방금 나눈 대화(참고용)]")
        for question, answer in recent_consultation:
            lines.append(f"사용자: {question}")
            lines.append(f"Brain: {answer}")

    return "\n".join(lines)
