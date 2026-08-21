"""Chief Brain이 사용자의 수정 요청을 판단해 만든 작은 수정 계획.

ChiefBrainPlan(needs_more_info/ready/objective/execution_mode/steps/
clarification_question/user_reply)을 억지로 재사용하지 않는다 - 이번
계획은 "이미 진행 중인 project의 development 결과 하나를 어떻게
고칠지"만 판단하는 훨씬 좁은 범위이고, ChiefBrainPlan의 execution_mode
판단(round33)/한방 개발 방지 검증(round33 validate_chief_brain_plan)은
"새 프로젝트 전체를 계획하는" 상황을 위한 것이라 이 좁은 revision
판단에 억지로 끼워 맞추면 안 된다(38단계 §7 - "revision은 새 project
전체 plan으로 취급하면 안 된다").

steps에는 BrainTaskStep을 그대로 재사용한다(새 step 모델을 만들지
않는다) - MainWindow가 이 steps를 승인 후 실제로 실행할 때는, 이
steps만 담은 별도의 임시 ChiefBrainPlan(execution_mode="project")을
코드에서 직접 구성해 기존 ChiefBrainOrchestrator/OrchestrationService에
그대로 넘긴다(round34 project checkpoint/round36 waiting_for_review를
그대로 재사용하기 위해서다) - 이 구성 과정은 LLM이 만드는 일반
계획과 달리 validate_chief_brain_plan()을 거치지 않는다(그 함수는
OpenAIChiefBrainProvider의 LLM 출력 검증 전용이지, Orchestrator가
자동으로 요구하는 게이트가 아니다).

필드 순서(judgment -> impact_summary -> steps)는 OpenAI Structured
Outputs가 선언 순서대로 토큰을 생성하는 특성(round16/round33에서 확인된
원칙과 동일) 때문이다 - "무엇을 왜 고칠지" 판단이 "구체적으로 어떤
step을 만들지"보다 먼저 서야 한다.
"""

from pydantic import BaseModel

from .brain_task_step import BrainTaskStep


class DevelopmentRevisionPlan(BaseModel):
    judgment: str
    impact_summary: str
    steps: list[BrainTaskStep]
