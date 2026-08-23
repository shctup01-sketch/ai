"""체크포인트 등에서 사용자가 Brain에게 "질문"할 때 쓰는 입력(58단계).

ChiefBrainProvider.plan_work(messages)와 다른 별개의 계약이다 - plan_work는
항상 ChiefBrainPlan(steps 포함)을 새로 만들어야 해서 단순 질문에도
"계획 생성"이라는 무거운 스키마를 강제한다. 이 요청은 그 반대로,
project_context(요약 문자열, checkpoint_context.py.build_brain_question_context()가
만든다)와 question 두 가지만 담아 "지금 상태를 설명"하는 훨씬 가벼운
용도로 쓴다. project_context는 이미 규칙 기반으로 압축된 요약 텍스트이지,
저장된 project state 전체 JSON이 아니다(§3/§4 - 토큰 낭비 금지).
"""

from pydantic import BaseModel


class BrainQuestionRequest(BaseModel):
    project_context: str
    question: str
