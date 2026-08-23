"""Development step의 실제 검수 증거를 후속 Analysis에 전달하기 위한
최소 snapshot(54단계).

실제 GameBlock 장기 프로젝트에서 확인된 문제: 52단계로 Development ->
Analysis dependency 연결 자체는 됐지만, 후속 Analysis는 DeveloperResult의
산출물 필드(summary/project_path/entry_point/created_files/modified_files/
errors)만 받았을 뿐 "실행해서 확인"으로 검증된 실행 성공 여부, Brain이
화면에서 관찰한 기능, revision으로 반영된 수정 내용은 전혀 받지 못했다.
그 결과 이미 확인된 기능(퀘스트/전투/보상/해금 등)을 Analysis가 "검증할
수 없음"으로 판단해 다음 Development가 이미 있는 기능을 처음부터
다시 만들자고 제안하는 문제가 실제로 발생했다.

DeveloperResult를 그대로 상속한다(§6 - 기존 schema를 대규모 변경하지
않는다) - 그래서 기존에 DeveloperResult만 duck-typing으로 판별하던
곳(analysis_executor.py._is_development_result_shaped, main_window.py의
isinstance(result, DeveloperResult) 체크 등)을 전혀 고치지 않아도 이
snapshot이 "development 결과"로 그대로 인식된다. 새로 추가한 필드는
전부 선택적이고 기본값이 "증거 없음"을 뜻한다(False/None/[]) - 실제로
존재하지 않는 실행 검증/화면 검수/수정 이력을 지어내지 않는다(§7).

56단계 - 54단계 이전에 완료된 Development는 evidence 없이 저장돼
있을 수 있다(project_state_store.py에 구형 DeveloperResult ->
DevelopmentEvidenceSnapshot 자동 migration/backfill 코드가 없음을
직접 확인). find_first_development_dependency()/
carry_forward_revision_evidence()는 "재개발 없이 다시 실행해서
확인"만으로 evidence를 새로 만들 때 쓰는 보조 함수다 - 둘 다 새
AI 호출/Provider와 무관한 순수 판별·병합 로직이다.
"""

from .brain_task_step import BrainTaskStep
from .developer_result import DeveloperResult
from .development_revision_summary import DevelopmentRevisionSummary
from .execution_result import ExecutionResult
from .orchestration_step_result import OrchestrationStepResult
from .screen_observation_result import ScreenObservationResult


class DevelopmentEvidenceSnapshot(DeveloperResult):
    """DeveloperResult의 산출물 필드에 더해, 실제로 존재하는 실행
    검증/화면 검수/수정 이력 증거만 선택적으로 담는다.

    사용자가 화면에서 직접 눌러봤다는 사실과 Brain이 화면 분석으로
    관찰한 사실을 동일시하지 않는다(§7) - visual_review_summary/
    observed_features는 어디까지나 "Brain 화면 분석 결과"이지 "사용자
    검수 완료"라는 표현을 쓰지 않는다.
    """

    runtime_checked: bool = False
    runtime_success: bool | None = None
    runtime_summary: str | None = None

    visual_review_summary: str | None = None
    observed_features: list[str] = []

    revision_requested: str | None = None
    revision_summary: str | None = None


def build_development_evidence_snapshot(
    dev_result: DeveloperResult,
    execution_result: ExecutionResult | None = None,
    observation_result: ScreenObservationResult | None = None,
    revision_summary: DevelopmentRevisionSummary | None = None,
) -> DevelopmentEvidenceSnapshot:
    """지금까지 실제로 모인 증거만 골라 하나의 snapshot으로 합친다.

    execution_result/observation_result/revision_summary가 None이면
    그 종류의 증거는 아예 없다는 뜻이고, 없는 필드는 기본값(False/None/
    빈 목록) 그대로 남는다 - 증거를 지어내지 않는다(§7/§10).
    """
    return DevelopmentEvidenceSnapshot(
        status=dev_result.status,
        summary=dev_result.summary,
        project_path=dev_result.project_path,
        entry_point=dev_result.entry_point,
        created_files=list(dev_result.created_files),
        modified_files=list(dev_result.modified_files),
        errors=list(dev_result.errors),
        runtime_checked=execution_result is not None,
        runtime_success=(execution_result.status == "success") if execution_result is not None else None,
        runtime_summary=execution_result.summary if execution_result is not None else None,
        visual_review_summary=observation_result.summary if observation_result is not None else None,
        observed_features=list(observation_result.observations) if observation_result is not None else [],
        revision_requested=revision_summary.requested_change if revision_summary is not None else None,
        revision_summary=revision_summary.summary if revision_summary is not None else None,
    )


def has_usable_development_evidence(step: BrainTaskStep, completed_steps: list[OrchestrationStepResult]) -> bool:
    """55단계 - step이 의존하는 Development 결과 중 하나라도 실제
    runtime/visual/revision evidence를 갖고 있는지 확인한다(preflight).

    54단계 이전에 완료된 Development 결과는 completed_steps에 순수
    DeveloperResult로만 남아 있다 - project_state_store.py에는 옛
    DeveloperResult를 DevelopmentEvidenceSnapshot으로 자동 변환하는
    migration/backfill 코드가 없다(직접 확인, 55단계 §1). 그래서
    DevelopmentEvidenceSnapshot이 아니면(순수 DeveloperResult거나 다른
    모양) 무조건 evidence 없음으로 본다 - isinstance만으로는 부족하고
    (snapshot이어도 evidence 필드가 전부 기본값일 수 있다), 실제 evidence
    필드 중 하나라도 채워져 있어야 True다. depends_on 여러 개 중
    하나라도 evidence가 있으면 재검토 가치가 있다고 보고 True를
    돌려준다(§2 - 있는 것만 확인, 없는 것을 만들어내지 않는다).
    """
    results_by_id = {entry.step_id: entry.result for entry in completed_steps}
    for dep_id in step.depends_on:
        result = results_by_id.get(dep_id)
        if not isinstance(result, DevelopmentEvidenceSnapshot):
            continue
        if result.runtime_checked or result.visual_review_summary or result.revision_requested or result.revision_summary:
            return True
    return False


def find_first_development_dependency(
    step: BrainTaskStep, completed_steps: list[OrchestrationStepResult]
) -> OrchestrationStepResult | None:
    """56단계 §5 - step이 의존하는 첫 Development 결과를 찾는다.

    depends_on에 Development step이 여러 개 있어도 첫 번째만 지원한다
    (§5 - 복잡하면 선택 UI를 만들지 말고 한계를 보고한다). Development
    dependency가 아예 없으면 None(재검수를 제안할 근거 자체가 없다는
    뜻) - 지어내지 않는다.
    """
    entries_by_id = {entry.step_id: entry for entry in completed_steps}
    for dep_id in step.depends_on:
        entry = entries_by_id.get(dep_id)
        if entry is not None and entry.task_type == "development":
            return entry
    return None


def carry_forward_revision_evidence(
    new_snapshot: DevelopmentEvidenceSnapshot, previous_result: object
) -> DevelopmentEvidenceSnapshot:
    """56단계 §11 - 재검수로 새 runtime/visual evidence를 만들 때, 이전에
    이미 있던 revision evidence(실제 revision이 있었을 때만 존재)를
    지우지 않는다. 이번 세션에서 새 revision 정보가 없으면(재검수
    중에는 수정 요청을 시작하지 않는다, §15) 새로 지어내지 않고 이전
    값을 그대로 이어간다 - 이전 결과가 DevelopmentEvidenceSnapshot이
    아니거나(순수 DeveloperResult) revision evidence 자체가 없었으면
    아무 것도 하지 않는다.
    """
    if not isinstance(previous_result, DevelopmentEvidenceSnapshot):
        return new_snapshot
    if new_snapshot.revision_requested or new_snapshot.revision_summary:
        return new_snapshot
    if not (previous_result.revision_requested or previous_result.revision_summary):
        return new_snapshot
    return new_snapshot.model_copy(
        update={
            "revision_requested": previous_result.revision_requested,
            "revision_summary": previous_result.revision_summary,
        }
    )
