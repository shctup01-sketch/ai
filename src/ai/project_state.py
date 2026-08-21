"""장기 project 진행 상태를 표현하는 순수 데이터 모델(41단계).

디스크에 안전하게 저장 가능한 값만 담는다(§4) - 화면 캡처 이미지 객체나
base64 screenshot/API Key 등은 이 모델 어디에도 없다. ChiefBrainPlan/
OrchestrationStepResult는 이미 검증된 pydantic 모델을 그대로 재사용한다
(model_dump/model_validate, §9) - 새로 손으로 중복 필드를 만들지 않는다.
PySide6를 전혀 알지 못한다(순수 Python) - MainWindow의 화면 캡처 객체
표시 계층과 완전히 분리되어 있다.

execution_mode를 Literal["project"]로 고정한 이유(§12) - task 모드는
장기 프로젝트 저장 대상이 아니다. task 모드 plan을 여기 넣으려 하면
pydantic이 그 자리에서 검증 오류로 막아준다(별도 if 분기를 여러 곳에
반복해서 두지 않아도 되는, 타입 수준의 안전장치).

schema_version은 v1 고정값이다(§8) - 저장 구조가 바뀌면 이 값을 올리고,
ProjectStateStore.load()가 지원하지 않는 값을 만나면 명확한 오류를
낸다(조용히 오작동하지 않는다).
"""

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel

from .chief_brain_plan import ChiefBrainPlan
from .orchestration_result import OrchestrationResult
from .orchestration_step_result import OrchestrationStepResult

SCHEMA_VERSION = 1

# OrchestrationStepResult/OrchestrationResult.status(StepStatus)와 별개의
# 타입이다 - "not_started"(계획만 만들어지고 아직 한 번도 실행되지 않은
# 상태, §11 "project plan 생성 완료" 저장 지점)까지 표현해야 하는데,
# StepStatus는 "이미 실행된 step 하나의 결과"만 나타내는 값이라 이
# 값을 추가할 이유가 없다(공유 타입을 이 모델 하나를 위해 넓히지
# 않는다).
ProjectOrchestrationStatus = Literal[
    "not_started", "completed", "waiting_for_approval", "waiting_for_review", "waiting_for_executor", "failed", "blocked"
]


class PersistentProjectState(BaseModel):
    schema_version: int = SCHEMA_VERSION
    project_id: str
    project_name: str
    created_at: str
    updated_at: str

    execution_mode: Literal["project"]
    plan: ChiefBrainPlan

    orchestration_status: ProjectOrchestrationStatus
    completed_steps: list[OrchestrationStepResult]

    current_step_id: str | None
    waiting_reason: str | None

    project_path: str | None
    last_user_request: str | None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_project_state(
    plan: ChiefBrainPlan,
    orchestration_result: OrchestrationResult | None,
    project_path: str | None,
    last_user_request: str | None,
    project_id: str | None = None,
    project_name: str | None = None,
    created_at: str | None = None,
) -> PersistentProjectState:
    """현재 실제로 갖고 있는 값만으로 PersistentProjectState를 만든다.

    orchestration_result가 없으면(아직 한 번도 실행되지 않은 갓 만들어진
    계획, §11 "project plan 생성 완료" 시점) orchestration_status는
    "not_started"이고 completed_steps는 빈 목록이다 - 없는 실행 결과를
    지어내지 않는다. project_name은 별도로 주어지지 않으면 plan.objective를
    그대로 쓴다(ChiefBrainPlan에 별도 "제목" 필드가 없으므로, 존재하지
    않는 데이터를 새로 지어내는 대신 이미 있는 objective를 재사용한다).
    """
    now = _utc_now_iso()

    if orchestration_result is None:
        orchestration_status: ProjectOrchestrationStatus = "not_started"
        completed_steps: list[OrchestrationStepResult] = []
        current_step_id = None
        waiting_reason = None
    else:
        orchestration_status = orchestration_result.status
        completed_steps = orchestration_result.completed_steps
        current_step_id = orchestration_result.pending_step_id
        waiting_reason = orchestration_result.summary if orchestration_status != "completed" else None

    return PersistentProjectState(
        project_id=project_id or str(uuid.uuid4()),
        project_name=project_name or plan.objective,
        created_at=created_at or now,
        updated_at=now,
        # plan.execution_mode를 그대로 전달한다(하드코딩된 "project"가
        # 아니다) - task 모드 plan이 실수로 여기 들어오면
        # execution_mode: Literal["project"]가 곧바로 ValidationError로
        # 막아준다(§12의 타입 수준 안전장치가 실제로 동작하려면 여기서
        # plan의 값을 있는 그대로 넘겨야 한다).
        execution_mode=plan.execution_mode,
        plan=plan,
        orchestration_status=orchestration_status,
        completed_steps=completed_steps,
        current_step_id=current_step_id,
        waiting_reason=waiting_reason,
        project_path=project_path,
        last_user_request=last_user_request,
    )
