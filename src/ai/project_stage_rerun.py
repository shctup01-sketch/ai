"""장기 project의 완료된 research step(과 그에 의존하는 step들)을 최신
Studio 기능으로 다시 실행하기 위해, "다시 실행 대상"과 그에 의존하는
"영향 대상"을 계산하는 순수 규칙 기반 헬퍼(45단계).

원본 ChiefBrainPlan/BrainTaskStep은 이 파일이 아예 참조만 할 뿐 전혀
수정하지 않는다(§2/§3 - 새 plan을 만들지 않는다, step_id/depends_on을
바꾸지 않는다). 이 파일은 plan.steps의 depends_on 관계만 읽어서 "다시
실행해야 하는 step_id 집합"을 계산하고, completed_steps에서 그 집합을
제외한 "보존할 결과" 목록을 만들 뿐이다 - 새 Orchestrator/Provider/
Worker 시스템을 전혀 만들지 않는다(§12/§22). 계산 결과는
main_window.py가 기존 ChiefBrainOrchestrator.resume_after_review()에
"축소된 completed_steps"로 그대로 넘기는 데 쓰인다 - resume_after_review()는
이미 "completed_steps에 없는 step_id는 처음부터 다시 실행한다"는 동작을
갖고 있으므로(chief_brain_orchestrator.py의 _run_from() - step_results에
없는 step은 실제로 실행된다), 이 파일이 직접 재실행 로직을 만들 필요가
없다.
"""

from .chief_brain_plan import ChiefBrainPlan
from .orchestration_step_result import OrchestrationStepResult

RESEARCH_TASK_TYPE = "research"


def find_rerun_root_step_ids(completed_steps: list[OrchestrationStepResult]) -> set[str]:
    """이미 완료(status=="completed")된 research step의 step_id를 전부 찾는다.

    research가 여러 개 있으면 전부 대상이다(§9 - 임의로 첫 번째 하나만
    고르지 않는다). research가 아니거나 아직 완료되지 않은(실패/대기)
    step은 "다시 실행할 근거 결과"가 없으므로 대상이 아니다.
    """
    return {
        entry.step_id
        for entry in completed_steps
        if entry.task_type == RESEARCH_TASK_TYPE and entry.status == "completed"
    }


def compute_affected_step_ids(plan: ChiefBrainPlan, root_step_ids: set[str]) -> set[str]:
    """root_step_ids(다시 실행할 research)와, plan.steps의 depends_on을 따라
    그것에 직접/간접으로 의존하는 모든 step_id를 함께 돌려준다(§4).

    실제 dependency graph(depends_on)를 사용한다 - "root 이후 순서의 모든
    step을 무조건 무효화"하는 fallback은 쓰지 않는다. 이 Studio의
    ChiefBrainPlan은 depends_on을 항상 채워서 만들어지므로(
    chief_brain_instructions.py가 Chief Brain에게 depends_on을 명시하도록
    지시하고, 이번 세션 전체에서 depends_on 없이 만들어진 plan은 없었다)
    graph 기반 계산만으로 충분하다 - 완료 보고에 이 판단 근거를 남긴다.
    """
    if not root_step_ids:
        return set()

    dependents: dict[str, list[str]] = {}
    for step in plan.steps:
        for dep_id in step.depends_on:
            dependents.setdefault(dep_id, []).append(step.step_id)

    affected = set(root_step_ids)
    queue = list(root_step_ids)
    while queue:
        current = queue.pop()
        for dependent_id in dependents.get(current, []):
            if dependent_id not in affected:
                affected.add(dependent_id)
                queue.append(dependent_id)
    return affected


def build_rerun_candidate_completed_steps(
    completed_steps: list[OrchestrationStepResult], affected_step_ids: set[str]
) -> list[OrchestrationStepResult]:
    """영향받지 않는(=그대로 보존할) completed_steps만 남긴다(§5/§7).

    원본 completed_steps 리스트/그 안의 OrchestrationStepResult 객체는
    수정하지 않는다 - 새 리스트에 기존 항목을 그대로(참조) 담기만 한다.
    순서는 원본 그대로 유지한다(§6 - resume_after_review()가 이 목록을
    그대로 seed로 쓴다).
    """
    return [entry for entry in completed_steps if entry.step_id not in affected_step_ids]


def summarize_research_step_results(completed_steps: list[OrchestrationStepResult]) -> dict[str, int]:
    """47단계 §4 - completed_steps 안의 research step들을 step_id ->
    유효 검색 결과 건수로 요약한다(실패 Dialog의 "조사 결과:" 절에서
    쓴다). 새 세션 상태/DB를 따로 만들지 않는다 - 이미 결과 안에 있는
    값을 매 호출 시점에 다시 계산할 뿐이다. status와 무관하게(완료가
    아니어도) research 모양(dict + search_results 키)이면 포함한다 -
    실패 진단에서는 "무엇을 실제로 봤는지"가 중요하다.
    """
    summary: dict[str, int] = {}
    for entry in completed_steps:
        if entry.task_type != RESEARCH_TASK_TYPE:
            continue
        result = entry.result
        if isinstance(result, dict) and "search_results" in result:
            summary[entry.step_id] = len(result.get("search_results") or [])
    return summary


def format_elapsed_seconds(elapsed_seconds: float) -> str:
    """46단계 §13 - 재실행 소요시간을 사람이 읽는 짧은 문장으로 만든다.

    각 API 호출별 정밀 telemetry는 만들지 않는다 - time.monotonic()으로
    잰 전체(또는 실패 시점까지의) 경과 시간 하나만 다룬다.
    """
    total_seconds = max(0, int(elapsed_seconds))
    minutes, seconds = divmod(total_seconds, 60)
    if minutes:
        return f"{minutes}분 {seconds}초"
    return f"{seconds}초"
