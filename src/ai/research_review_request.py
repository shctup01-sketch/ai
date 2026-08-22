"""ResearchReviewer(조사 결과 분석 AI)에게 전달할 입력.

ResearchWorker가 반환한 실제 검색 결과(Task.result["search_results"])를
가공 없이 그대로 담는다 - 검색 결과를 요약하거나 일부를 삭제해서
전달하면 Reviewer가 근거 없는 판단을 내릴 위험이 커지기 때문이다.

48단계 - dependency_context(기본값 "")는 이전 analysis 결과(Analysis ->
Analysis dependency)를 담기 위한 선택적 필드다. 이미 잘 동작하는
Research -> Analysis 흐름(search_results/query)은 전혀 건드리지 않고,
기존 필드를 오염시키지 않는 별도 필드만 추가했다 - 기본값이 빈
문자열이라 이 필드를 모르는 기존 호출부(main_window.py의 단일 Research
UI 흐름 등)는 그대로 동작한다.
"""

from pydantic import BaseModel


class ResearchReviewRequest(BaseModel):
    task_title: str
    task_goal: str
    query: str
    search_results: list[dict]
    dependency_context: str = ""
