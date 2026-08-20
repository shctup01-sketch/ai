"""Chief Brain이 캡처된 화면 이미지를 보고 판단한 결과.

ChiefBrainPlan(needs_more_info/ready/objective/steps/clarification_question/
user_reply)을 억지로 재사용하지 않는다 - ChiefBrainPlan은 "다음에 무엇을
할지 계획하는" 계약이고, 이 모델은 "지금 화면에서 무엇을 봤는지 기록하는"
계약이라 성격이 다르다. ResearchReviewResult(research_review_result.py)와
같은 이유로 별도 모델을 둔다: 필드가 명확한 이름을 가지고 있어야
StepContext 직렬화(step_context.py)와 후속 step(analysis/development)
전달이 깔끔해진다.
"""

from pydantic import BaseModel


class ScreenObservationResult(BaseModel):
    summary: str
    observations: list[str]
    issues: list[str]
    next_action: str
