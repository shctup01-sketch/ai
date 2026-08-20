"""Chief Brain 계획(ChiefBrainPlan)을 구성하는 작업 한 단계.

TaskSystem의 Task와는 다른 모델이다 - BrainTaskStep은 아직 실행되지 않은
"계획 상의 한 단계"이고, Task는 TaskManager에 실제로 등록되어 실행되는
단위다. Chief Brain이 계획을 다 세운 뒤, 이후 도입될 Orchestrator가
BrainTaskStep을 보고 실제 Task를 만드는 것을 상정한다(이번 v1 단계에서는
그 연결까지 만들지 않는다).

task_type은 Literal로 닫지 않고 str로 둔다 - development/research 외에
business/file_management/browser/email/kakao/kmong/document/analysis 등
앞으로 추가될 어떤 작업 종류가 와도 이 모델을 다시 정의할 필요가 없게
하기 위해서다. 아직 그 task_type을 처리할 Worker가 없어도(WorkerRegistry에
등록되어 있지 않아도) 계획 자체는 표현할 수 있어야 한다 - 실행 시점에
Worker가 없으면 TaskExecutor가 이미 안전하게 실패 처리한다(worker_registry.py/
task_executor.py 참고).
"""

from pydantic import BaseModel


class BrainTaskStep(BaseModel):
    step_id: str
    order: int
    task_type: str
    title: str
    goal: str
    depends_on: list[str]
    requires_approval: bool
    approval_reason: str | None
