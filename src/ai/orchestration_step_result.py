"""ChiefBrainOrchestrator가 계획의 step 하나를 처리한 결과.

Task(task.py)와는 다른 모델이다 - Task는 TaskManager가 실제로 관리하는
실행 단위이고, OrchestrationStepResult는 Orchestrator가 그 step을
"어떻게 처리했는지"에 대한 기록이다. 승인 대기(waiting_for_approval)나
실행기 없음(waiting_for_executor), 선행 작업 미완료(blocked) 상태는
애초에 Task조차 만들어지지 않으므로 task_id가 비어 있을 수 있다.

status는 Orchestrator 자신이 만들어내는 값이라(LLM이 자유롭게 채우는
값이 아니다) task_type처럼 열어둘 이유가 없다 - 오타 방지를 위해
Literal로 닫는다.
"""

from typing import Literal

from pydantic import BaseModel

StepStatus = Literal["completed", "waiting_for_approval", "waiting_for_executor", "failed", "blocked"]


class OrchestrationStepResult(BaseModel):
    step_id: str
    task_type: str
    status: StepStatus
    task_id: str | None
    result: object | None
    error: str | None
    requires_approval: bool
    approval_reason: str | None
