"""ChiefBrainOrchestrator가 계획의 step 하나를 처리한 결과.

Task(task.py)와는 다른 모델이다 - Task는 TaskManager가 실제로 관리하는
실행 단위이고, OrchestrationStepResult는 Orchestrator가 그 step을
"어떻게 처리했는지"에 대한 기록이다. 승인 대기(waiting_for_approval)나
실행기 없음(waiting_for_executor), 선행 작업 미완료(blocked) 상태는
애초에 Task조차 만들어지지 않으므로 task_id가 비어 있을 수 있다.

status는 Orchestrator 자신이 만들어내는 값이라(LLM이 자유롭게 채우는
값이 아니다) task_type처럼 열어둘 이유가 없다 - 오타 방지를 위해
Literal로 닫는다.

36단계 - "waiting_for_review"는 "waiting_for_approval"과 의미가 다르다.
waiting_for_approval은 아직 그 step을 시작하지도 않은 상태(승인 대기)고,
waiting_for_review는 project 모드 development step이 이미 성공적으로
"completed"된 뒤 다음 step으로 넘어가기 전 결과 검토를 기다리는
OrchestrationResult 전체의 상태다 - 그 step 자신의
OrchestrationStepResult.status는 "completed"로 그대로 남는다(실제로
개발이 끝났고, 이후 depends_on이 이 결과를 정상 참조해야 하므로).
"""

from typing import Literal

from pydantic import BaseModel

StepStatus = Literal[
    "completed", "waiting_for_approval", "waiting_for_review", "waiting_for_executor", "failed", "blocked"
]


class OrchestrationStepResult(BaseModel):
    step_id: str
    task_type: str
    status: StepStatus
    task_id: str | None
    result: object | None
    error: str | None
    requires_approval: bool
    approval_reason: str | None
