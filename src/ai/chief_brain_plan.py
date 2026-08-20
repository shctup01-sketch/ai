"""Chief Brain의 구조화된 계획 응답 형식(OpenAI Structured Outputs로 강제).

필드 순서는 BrainResponse(brain_response.py)에서 얻은 교훈을 그대로
따른다 - OpenAI Structured Outputs는 JSON schema의 property 순서대로
토큰을 생성하므로, "판단"에 해당하는 필드(needs_more_info/ready/
objective/steps)를 자연어 답변(user_reply)보다 앞에 둔다. user_reply를
먼저 두면 모델이 계획을 확정하기도 전에 답변부터 써버려, 그 답변에
맞춰 뒤늦게 계획을 끼워 맞추는 문제가 생길 수 있다(BrainResponse에서
실기로 반복 확인된 문제와 동일한 유형).

steps는 BrainTaskStep 목록이다 - 아직 이 계획을 실제로 연속 실행하는
Orchestrator는 이번 단계에 없다(다음 단계에서 만든다). 이 모델은
"계획을 세우는 능력"까지만 담당한다.

33단계 - execution_mode: "task"(소형 업무, 기존처럼 자동 연속 실행)
또는 "project"(대형 프로젝트, 한 번에 전체 개발 금지)를 나타낸다.
기본값을 "task"로 둬서, 이 필드를 모르는 기존 테스트/Fake 코드가
ChiefBrainPlan(...)을 execution_mode 없이 그대로 생성해도 깨지지
않는다(하위 호환) - Python 쪽에서 키워드 인자로만 생성하므로 필드
위치 자체는 순서 문제가 없지만, OpenAI Structured Outputs는 필드
"선언 순서"대로 토큰을 생성하므로(위 문단이 설명하는 것과 동일한
원리) execution_mode는 반드시 steps보다 앞에 둔다 - project/task
판단이 먼저 서야 그 판단에 맞게 steps를 분해할 수 있고, 그 반대로
steps부터 만든 뒤 뒤늦게 execution_mode를 끼워 맞추면 7단계가 금지한
"project인데 development 1개로 끝내는" 실패 패턴이 그대로 재현될
위험이 있다.
"""

from typing import Literal

from pydantic import BaseModel

from .brain_task_step import BrainTaskStep


class ChiefBrainPlan(BaseModel):
    needs_more_info: bool
    ready: bool
    objective: str
    execution_mode: Literal["task", "project"] = "task"
    steps: list[BrainTaskStep]
    clarification_question: str | None
    user_reply: str


def validate_chief_brain_plan(plan: ChiefBrainPlan) -> list[str]:
    """계획의 최소한의 구조적 정합성만 검사한다(과도한 workflow 검증 엔진이 아니다).

    반환값이 빈 리스트면 통과다. 어떤 필드를 어떻게 채워야 하는지에 대한
    "내용" 판단(예: 이 요청이 정말 research가 맞는지)은 여기서 하지
    않는다 - 그건 지시문(chief_brain_instructions.py)과 모델의 몫이다.
    """
    errors: list[str] = []

    if not plan.objective.strip():
        errors.append("objective가 비어 있습니다.")

    step_ids = [step.step_id for step in plan.steps]
    seen_ids: set[str] = set()
    duplicate_ids: set[str] = set()
    for step_id in step_ids:
        if step_id in seen_ids:
            duplicate_ids.add(step_id)
        seen_ids.add(step_id)
    if duplicate_ids:
        errors.append(f"중복된 step_id가 있습니다: {sorted(duplicate_ids)}")

    orders = [step.order for step in plan.steps]
    if any(order < 0 for order in orders):
        errors.append("order 값에 음수가 있습니다.")
    if len(orders) != len(set(orders)):
        errors.append("중복된 order 값이 있습니다.")

    valid_step_ids = set(step_ids)
    for step in plan.steps:
        if step.step_id in step.depends_on:
            errors.append(f"step_id={step.step_id}가 자기 자신을 depends_on으로 참조합니다.")

        unknown_deps = [dep for dep in step.depends_on if dep not in valid_step_ids]
        if unknown_deps:
            errors.append(
                f"step_id={step.step_id}의 depends_on이 존재하지 않는 step_id를 참조합니다: {unknown_deps}"
            )

        if not step.title.strip():
            errors.append(f"step_id={step.step_id}의 title이 비어 있습니다.")
        if not step.goal.strip():
            errors.append(f"step_id={step.step_id}의 goal이 비어 있습니다.")

    # 33단계 - 7단계 "한방 개발 방지"의 최소 코드 안전장치. project
    # 모드인데 development 단 1개로만 계획이 끝나면(설계/검증 등 없이
    # "게임 엔진 만들어줘" -> development 1개로 전체를 개발하려는 실패
    # 패턴) 구조적으로 거부한다. task 모드는 원래도 development 1개짜리
    # 계획을 허용해야 하므로(예: "뱀게임 만들어줘") 이 검사에서 완전히
    # 제외한다.
    if plan.execution_mode == "project" and len(plan.steps) == 1 and plan.steps[0].task_type == "development":
        errors.append(
            "project 모드 계획이 development 1개 step으로만 구성되어 있습니다 - "
            "대형 프로젝트는 설계/검증 등을 거치지 않고 development 하나로 끝낼 수 없습니다."
        )

    return errors
