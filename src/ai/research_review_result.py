"""ResearchReviewer의 구조화된 응답 형식(OpenAI Structured Outputs로 강제).

필드는 최소한만 둔다 - Reviewer가 "확인 가능한 사실 요약"과 "AI의 판단
(추천/이유/리스크)"을 뒤섞지 않도록, 관찰(market_observations)과
판단(recommended_idea/recommendation_reason)을 서로 다른 필드로 분리한다.
"""

from pydantic import BaseModel


class ResearchReviewResult(BaseModel):
    summary: str
    market_observations: list[str]
    candidate_ideas: list[str]
    recommended_idea: str
    recommendation_reason: str
    risks: list[str]
    next_action: str
