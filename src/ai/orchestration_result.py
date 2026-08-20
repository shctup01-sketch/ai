"""ChiefBrainOrchestrator.run() 전체 실행 결과.

completed_steps는 "성공한 step만"이 아니라 "Orchestrator가 실제로 처리를
시도해 결과가 생긴 step 전부"를 순서대로 담는다(예: 2번째 step에서
waiting_for_executor로 멈췄다면 completed_steps에는 1번째 성공 결과와
2번째 waiting_for_executor 결과 2개가 담긴다). 아직 처리되지 않은 이후
step은 여기 담기지 않는다.
"""

from pydantic import BaseModel

from .orchestration_step_result import OrchestrationStepResult, StepStatus


class OrchestrationResult(BaseModel):
    status: StepStatus
    completed_steps: list[OrchestrationStepResult]
    pending_step_id: str | None
    summary: str
