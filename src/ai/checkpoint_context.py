"""project checkpoint 승인 Dialog 등에서 이전 step 결과를 사람이 읽을
수 있는 텍스트로 보여주기 위한 순수 규칙 기반 헬퍼(42단계).

새 AI 요약/비교 호출을 하지 않는다(§4/§6/§15) - 이미 있는 결과 객체
(ResearchReviewResult/DeveloperResult/ScreenObservationResult는 모두
"summary" 필드를 갖고 있다 - 각 모델 정의 참고)의 summary 필드를
우선 쓰고, research task의 결과(순수 dict - research_worker.py 참고,
필드: task_type/title/goal/query/search_results)는 title/goal/query/
search_results만 규칙 기반으로 뽑는다(기존 _show_research_result_popup의
표시 방식과 같은 형식을 재사용한다). 없는 필드를 지어내지 않는다.
"""

from pydantic import BaseModel

from .orchestration_step_result import OrchestrationStepResult


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
