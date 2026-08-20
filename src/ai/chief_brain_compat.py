"""ChiefBrainPlan을 기존 BrainResponse(development/research/general 3종)로 변환하는 호환 어댑터.

기존 Development/Research UI(ChatPanel/MainWindow)는 여전히 BrainResponse
하나만 알고 있고, 이번 단계에서 그 흐름을 전혀 건드리지 않는다
(brain_response.py/brain_instructions.py/openai_provider.py/chat_panel.py/
main_window.py 무변경). 대신 이 파일이 "ChiefBrainPlan의 결과 중 기존
UI가 이해할 수 있는 형태"만 골라 BrainResponse로 옮겨준다.

ChiefBrainPlan은 여러 단계(steps)를 표현할 수 있지만, 기존 BrainResponse는
Task 하나만 표현할 수 있다 - 그래서 steps가 2개 이상인 계획은 변환하지
않고 명시적으로 거부한다(자동으로 첫 step만 골라 나머지를 조용히 버리면
사용자가 계획 전체가 반영됐다고 착각할 수 있다). 여러 Task를 실제로
이어 실행하는 것은 이후 단계에서 만들 Orchestrator의 역할이다.
"""

from .brain_response import BrainResponse
from .chief_brain_plan import ChiefBrainPlan

_COMPATIBLE_STEP_TASK_TYPES = ("research", "development")


class ChiefBrainCompatError(Exception):
    """ChiefBrainPlan을 BrainResponse로 변환할 수 없을 때 발생한다."""


def adapt_chief_brain_plan_to_brain_response(plan: ChiefBrainPlan) -> BrainResponse:
    """ChiefBrainPlan 중 "단일 development/research 작업"에 해당하는 경우만 변환한다.

    - 추가 정보가 필요하거나(needs_more_info) 아직 준비되지 않은(ready=False)
      계획은 일반 대화 응답(plan_ready=False)으로 변환한다.
    - steps가 비어 있으면 순수 일반 대화로 본다.
    - steps가 정확히 1개이고 그 task_type이 research/development면 기존
      Research/Development 흐름 그대로 변환한다.
    - steps가 2개 이상이거나, 1개라도 task_type이 development/research가
      아니면(예: kmong_publish) 변환할 수 없다는 뜻으로 ChiefBrainCompatError를
      발생시킨다 - 조용히 일부만 반영하지 않는다.
    """
    if plan.needs_more_info or not plan.ready:
        return BrainResponse(
            task_type="general",
            is_dev_request=False,
            needs_more_info=plan.needs_more_info,
            plan_ready=False,
            reply_to_user=plan.clarification_question or plan.user_reply,
            project_name=None,
            requirements_summary=None,
            feature_list=None,
            task_steps=None,
            research_title=None,
            research_goal=None,
        )

    if not plan.steps:
        return BrainResponse(
            task_type="general",
            is_dev_request=False,
            needs_more_info=False,
            plan_ready=False,
            reply_to_user=plan.user_reply,
            project_name=None,
            requirements_summary=None,
            feature_list=None,
            task_steps=None,
            research_title=None,
            research_goal=None,
        )

    if len(plan.steps) > 1:
        raise ChiefBrainCompatError(
            "여러 단계로 이루어진 계획은 기존 BrainResponse(단일 작업) 형태로 "
            "변환할 수 없습니다 - 여러 Task를 잇는 연속 실행은 Orchestrator의 역할입니다."
        )

    step = plan.steps[0]
    if step.task_type not in _COMPATIBLE_STEP_TASK_TYPES:
        raise ChiefBrainCompatError(
            f"기존 BrainResponse는 development/research/general만 표현할 수 있어, "
            f"task_type={step.task_type!r}인 단계는 변환할 수 없습니다."
        )

    if step.task_type == "research":
        return BrainResponse(
            task_type="research",
            is_dev_request=False,
            needs_more_info=False,
            plan_ready=True,
            reply_to_user=plan.user_reply,
            project_name=None,
            requirements_summary=None,
            feature_list=None,
            task_steps=None,
            research_title=step.title,
            research_goal=step.goal,
        )

    # step.task_type == "development"
    return BrainResponse(
        task_type="development",
        is_dev_request=True,
        needs_more_info=False,
        plan_ready=True,
        reply_to_user=plan.user_reply,
        project_name=step.title,
        requirements_summary=step.goal,
        feature_list=[],
        task_steps=[],
        research_title=None,
        research_goal=None,
    )
