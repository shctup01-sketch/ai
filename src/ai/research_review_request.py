"""ResearchReviewer(조사 결과 분석 AI)에게 전달할 입력.

ResearchWorker가 반환한 실제 검색 결과(Task.result["search_results"])를
가공 없이 그대로 담는다 - 검색 결과를 요약하거나 일부를 삭제해서
전달하면 Reviewer가 근거 없는 판단을 내릴 위험이 커지기 때문이다.
"""

from pydantic import BaseModel


class ResearchReviewRequest(BaseModel):
    task_title: str
    task_goal: str
    query: str
    search_results: list[dict]
