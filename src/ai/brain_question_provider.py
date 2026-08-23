"""Brain 질문(58단계) 제공자 공통 인터페이스.

58단계(사용자 검토) - 이것은 "질문에 답하는 별도의 총괄 AI"가 아니라,
같은 Chief Brain의 "사용자 상담(질문 응답) 모드"를 위한 실행 경로다.
ChiefBrainProvider(plan_work)와 Request/Answer 모델·QThread Service를
기능별로 나눈 것뿐이다(계획 생성은 ChiefBrainPlan이라는 무거운
Structured Outputs 스키마가 필요하고, 질문 응답은 훨씬 가벼운 자유
답변이 필요해 출력 형태가 다르다) - 두 경로 모두 brain_question_
instructions.py/chief_brain_instructions.py가 공유하는
CHIEF_BRAIN_CORE_IDENTITY를 시스템 지시문 맨 앞에 두므로, "지금 판단을
내리는 주체"는 항상 하나의 같은 Chief Brain이다. Research/Analysis/
Development Executor와 달리, 이 Provider는 Orchestrator를 통해 실행되지
않고 Chief Brain이 사용자와 직접 대화할 때만 쓰인다.
"""

from abc import ABC, abstractmethod

from .brain_question_answer import BrainQuestionAnswer
from .brain_question_request import BrainQuestionRequest


class BrainQuestionProvider(ABC):
    """Chief Brain의 상담 모드 - 프로젝트 문맥 요약 + 질문을 주면 답변을 돌려준다."""

    @abstractmethod
    def answer(self, request: BrainQuestionRequest) -> BrainQuestionAnswer:
        raise NotImplementedError
