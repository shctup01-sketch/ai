"""ChiefBrainPlan을 실제 TaskSystem/Developer 실행으로 연결하는 Orchestrator.

이 파일은 TaskSystem과 (선택적으로) DevelopmentExecutor를 생성자에서
외부 주입받을 뿐, 내부에서 새로 만들지 않는다. OpenAI client/Provider를
전혀 알지 못하고(이 파일에는 OpenAI 관련 import가 없다),
MainWindow/ChatPanel/BrainService/DeveloperService/ExecutionService/
PackageFixService 무엇과도 연결되어 있지 않다 - 이번 단계도 "계획을
실제로 실행할 수 있는 엔진"까지만 만들고, UI 연결은 다음 단계로 미룬다.

v1 범위(중요, 의도적인 제약):
- 현재 TaskSystem에 실제로 등록된 Worker는 research 하나뿐이다.
  등록되지 않은 task_type을 억지로 아무 Worker에게나 보내지 않는다 -
  WorkerRegistry.has_worker()로 먼저 확인하고, 없으면
  "waiting_for_executor"로 멈춘다.
- development/analysis는 TaskSystem/WorkerRegistry를 거치지 않는다
  (TaskSystem은 여전히 이 둘을 Worker로 등록하지 않는다 - task_system.py
  무변경). 대신 development_executor/analysis_executor가 각각 주입되어
  있으면 그것을 통해서만 실행한다. 주입되어 있지 않으면 이전과 동일하게
  "waiting_for_executor"로 멈춘다 - 이 파일이 development/analysis를
  실행할 "코드"를 직접 만들지도, DeveloperService/ResearchReviewService를
  직접 알지도 않는다.
- requires_approval=True인 step은 자동 실행하지 않는다. 이 안에서
  "승인됐다"는 값을 스스로 만들어내지 않는다(approved=True 같은 것을
  하드코딩하지 않는다) - development/analysis 모두 예외 없이 이 규칙을
  먼저 통과해야 한다(DevelopmentExecutor/AnalysisExecutor는 승인 여부를
  전혀 판단하지 않는다).
- development/analysis step의 depends_on에 적힌, "완료된" 선행 step
  결과만 ExecutionContext(step_context.py)로 모아 각 Executor에
  전달한다 - step.goal 원본 문자열 자체는 절대 수정하지 않는다(원본을
  바꾸는 대신 별도 참고자료로 넘긴다). depends_on에 없는 step이나
  completed가 아닌 상태의 결과는 절대 섞이지 않는다. research 등 다른
  task_type(TaskSystem 경로)에는 아직 context를 전달하지 않는다.
- Developer가 코드를 생성했다고 해서 자동으로 프로그램을 실행하지
  않는다(entry_point 확인/venv/requirements 설치/실제 실행은 여전히
  별도 계층의 일이다 - 이 파일은 ExecutionService를 전혀 모른다).
- 어떤 step이든 order 순서상 이후 step은, 그 앞의 step이 정확히
  "completed"로 끝난 경우에만 진행한다. 승인 대기/실행기 없음/실패/
  (방어적으로 확인하는) 선행 작업 미완료 중 어떤 상태로든 멈추면 그
  즉시 전체 실행을 중단한다 - 이후 step은 아예 처리를 시도하지 않는다.

29단계 - resume(): requires_approval=True로 waiting_for_approval에서
멈춘 step(예: screen_observation)이 이 파일 밖에서(UI가 사용자 승인을
받고 실제로 실행해) 이미 "completed"가 된 뒤, 나머지 계획을 이어서
실행하기 위한 최소 재개 경로다. 이 파일은 이번에도 승인 여부를 스스로
판단하지 않는다 - 호출자가 이미 승인/실행을 마친 결과(완성된
OrchestrationStepResult)를 건네줄 때만 그 뒤를 잇는다. 이미 완료된
이전 step(예: 앞선 research)은 다시 실행하지 않는다 - run()과
resume()이 공유하는 _run_from()이 이미 step_results에 있는 step_id를
만나면 건너뛴다. 범용 Workflow Engine을 만들지 않는다 - "이미 아는
결과를 다시 실행하지 않고 다음 step으로 이어간다"는 한 가지 동작만
한다.

31단계 - on_stage_changed: run()/resume()에 선택적으로 넘길 수 있는 평범한
콜백(Callable[[str], None])이다. Qt Signal이 아니다 - 이 파일은 여전히
PySide6를 전혀 모른다(OrchestrationService가 QThread 안에서 자신의
stage_changed.emit을 그대로 이 콜백으로 넘겨줄 뿐이다). step을 실제로
실행하기 직전/성공 직후에만 호출한다("N/전체 task_type 시작"/"완료" 형태) -
승인 대기/실행기 없음/실패처럼 이미 다른 방식(waiting_for_approval 등
OrchestrationResult.status, 화면 승인 Dialog)으로 사용자에게 전달되는
상태까지 이 콜백이 중복해서 새 문구를 만들지는 않는다(승인 대기만
예외적으로 함께 알린다 - 사용자가 "지금 이 승인이 몇 번째 단계인지"
바로 알 수 있어야 하기 때문).

34단계 - project 체크포인트: execution_mode가 "project"인 계획은
development step에 도달하기 전까지 최소 한 번은 requires_approval로
멈춰야 한다(한방 개발 방지). Chief Brain이 이미 적절한 곳에
requires_approval=True를 뒀다면(_needs_project_checkpoint가
step_results 안에서 이미 한 번이라도 승인 대기를 거쳤는지로 판단)
중복 승인 지점을 추가하지 않는다. 이 안전장치가 만든 승인 대기는
원본 BrainTaskStep 객체를 수정하지 않고 OrchestrationStepResult
하나에만 requires_approval=True를 얹는다. 승인 후 재실행은 기존
resume()을 그대로 쓰지 않는다(resume()은 승인된 step이 이미
"completed"라고 가정하는 screen_observation 전용 계약이다) - 대신
새 resume_project_checkpoint()를 추가해 그 step을 "처음" 실행되게
한다. resume()의 기존 시그니처/동작은 전혀 바꾸지 않는다.

36단계 - 개발 결과 검토 checkpoint: project 모드에서 development
step이 성공(dev_result.status=="success")해도, 그 자리에서 바로 다음
step으로 넘어가지(continue) 않고 멈춘다(break). 그 step 자신의
OrchestrationStepResult.status는 "completed"로 그대로 둔다(개발은
실제로 끝났다 - 이후 step의 depends_on이 이 결과를 정상 참조해야
한다) - 대신 전체 OrchestrationResult.status만 "waiting_for_review"로
보고한다("승인 대기"=아직 시작 전과 다른, "이미 끝난 결과를
검토하는" 상태). task 모드는 이 일시정지를 전혀 타지 않는다(기존
그대로 continue). 사용자가 검토 후 계속 진행하면
resume_after_review()를 부른다 - completed_steps를 그대로 다시
seed하기만 하면 되므로(이미 끝난 development step도 포함해) 별도
step_id 인자가 필요 없다. _run_from의 "이미 처리된 step 건너뛰기"
규칙이 그 development step의 재실행을 그대로 막아준다.
"""

from typing import Callable

from .analysis_executor import AnalysisExecutionError, AnalysisExecutor
from .chief_brain_plan import ChiefBrainPlan
from .development_executor import DevelopmentExecutionError, DevelopmentExecutor
from .orchestration_result import OrchestrationResult
from .orchestration_step_result import OrchestrationStepResult, StepStatus
from .step_context import ExecutionContext, StepContext
from .task_system import TaskSystem

# development/analysis는 TaskSystem/WorkerRegistry가 아니라 별도의
# Executor 경로로 실행한다 - 이 값들만 이 파일이 알고 있어도 된다(다른
# 어떤 task_type도 여기서 특별 취급하지 않는다).
_DEVELOPMENT_TASK_TYPE = "development"
_ANALYSIS_TASK_TYPE = "analysis"

# 34단계 - project 모드 안전장치가 강제로 만든 승인 대기에 붙는 기본 이유.
# Chief Brain이 이 step에 approval_reason을 직접 써두지 않았을 때만 쓰인다.
_PROJECT_CHECKPOINT_REASON = "대형 프로젝트의 첫 실제 개발 단계입니다. 진행 전 확인이 필요합니다."


class ChiefBrainOrchestrator:
    """ChiefBrainPlan.steps를 order 순서대로 처리해 TaskSystem/Developer/Reviewer로 실행한다."""

    def __init__(
        self,
        task_system: TaskSystem,
        development_executor: DevelopmentExecutor | None = None,
        analysis_executor: AnalysisExecutor | None = None,
    ):
        self._task_system = task_system
        self._development_executor = development_executor
        self._analysis_executor = analysis_executor

    def run(
        self, plan: ChiefBrainPlan, on_stage_changed: Callable[[str], None] | None = None
    ) -> OrchestrationResult:
        if not plan.steps:
            return OrchestrationResult(
                status="completed",
                completed_steps=[],
                pending_step_id=None,
                summary="실행할 작업이 없는 계획입니다.",
            )

        return self._run_from(plan, {}, [], on_stage_changed)

    def resume(
        self,
        plan: ChiefBrainPlan,
        completed_steps: list[OrchestrationStepResult],
        approved_step_result: OrchestrationStepResult,
        on_stage_changed: Callable[[str], None] | None = None,
    ) -> OrchestrationResult:
        """requires_approval=True였던 step이 이미 승인/실행되어 완료된 뒤,
        나머지 계획을 이어서 실행한다.

        completed_steps: 직전 run()/resume() 호출이 돌려준
        OrchestrationResult.completed_steps다(마지막 항목이 이번에 승인된
        step의 "waiting_for_approval" 결과이며, approved_step_result로
        교체된다). approved_step_result: 승인 후 실제로 실행되어 만들어진
        "completed" 결과(예: 화면을 캡처해 분석한 ScreenObservationResult를
        감싼 것) - 이 메서드는 승인이 실제로 이루어졌는지 스스로 판단하지
        않는다. 호출자가 이미 승인/실행을 마친 뒤에만 불러야 한다.
        """
        step_results: dict[str, OrchestrationStepResult] = {}
        seeded_completed: list[OrchestrationStepResult] = []
        for prior in completed_steps:
            if prior.step_id == approved_step_result.step_id:
                continue
            step_results[prior.step_id] = prior
            seeded_completed.append(prior)

        step_results[approved_step_result.step_id] = approved_step_result
        seeded_completed.append(approved_step_result)

        return self._run_from(plan, step_results, seeded_completed, on_stage_changed)

    def resume_project_checkpoint(
        self,
        plan: ChiefBrainPlan,
        completed_steps: list[OrchestrationStepResult],
        approved_step_id: str,
        on_stage_changed: Callable[[str], None] | None = None,
    ) -> OrchestrationResult:
        """34단계 - project 체크포인트(안전장치 또는 step 자신의
        requires_approval=True) 승인 후, 그 step을 "처음" 실제로 실행한다.

        resume()과 다르다: resume()은 approved_step_result가 이미 UI
        쪽에서 실행까지 끝난 "completed" 결과라고 가정한다(예: 화면을
        캡처해 분석하는 승인 - 캡처/분석이 승인 직후 UI에서 이미
        일어난다). project 체크포인트의 development step은 승인이 곧
        "지금부터 이 step을 실행해도 된다"는 뜻일 뿐, 실행 자체는 아직
        전혀 일어나지 않았다 - 그래서 완성된 결과 대신 승인된
        step_id만 받고, completed_steps에서 그 step의
        waiting_for_approval 자리를 제거한 뒤 _run_from에
        bypass_approval_for로 넘겨 실제로 실행되게 한다. resume()의
        기존 시그니처/동작은 전혀 건드리지 않는다(화면 확인 승인
        경로는 무위험).
        """
        step_results: dict[str, OrchestrationStepResult] = {}
        seeded_completed: list[OrchestrationStepResult] = []
        for prior in completed_steps:
            if prior.step_id == approved_step_id:
                continue
            step_results[prior.step_id] = prior
            seeded_completed.append(prior)

        return self._run_from(
            plan, step_results, seeded_completed, on_stage_changed, bypass_approval_for=approved_step_id
        )

    def resume_after_review(
        self,
        plan: ChiefBrainPlan,
        completed_steps: list[OrchestrationStepResult],
        on_stage_changed: Callable[[str], None] | None = None,
    ) -> OrchestrationResult:
        """36단계 - project development 결과 검토("계속 진행") 후 나머지
        계획을 이어서 실행한다.

        resume_project_checkpoint()와 다르다: 여기서는 completed_steps의
        마지막 항목(방금 검토를 마친 development step)이 이미
        "completed"이고 실제 dev_result도 담고 있다 - 다시 실행할 필요가
        없으므로 제외/치환 없이 completed_steps를 그대로 seed한다.
        _run_from의 "이미 처리된 step은 건너뛴다" 규칙이 이 step의
        재실행을 막고, 그다음 아직 처리되지 않은 step부터 이어간다.
        """
        step_results: dict[str, OrchestrationStepResult] = {result.step_id: result for result in completed_steps}
        return self._run_from(plan, step_results, list(completed_steps), on_stage_changed)

    @staticmethod
    def _emit_stage(on_stage_changed: Callable[[str], None] | None, text: str) -> None:
        if on_stage_changed is not None:
            on_stage_changed(text)

    def _run_from(
        self,
        plan: ChiefBrainPlan,
        step_results: dict[str, OrchestrationStepResult],
        completed_steps: list[OrchestrationStepResult],
        on_stage_changed: Callable[[str], None] | None = None,
        bypass_approval_for: str | None = None,
    ) -> OrchestrationResult:
        # plan.steps를 정렬만 할 뿐 원본 리스트/step 객체는 어디서도
        # 수정하지 않는다(sorted()는 새 리스트를 반환한다).
        ordered_steps = sorted(plan.steps, key=lambda step: step.order)
        total_steps = len(ordered_steps)
        # 36단계 - project 모드 development 결과 검토를 위해 멈췄는지
        # 표시한다(None이 아니면 그 step_id에서 멈췄다는 뜻). "승인
        # 대기"(waiting_for_approval)와 구분되는 별도 상태이므로,
        # completed_steps[-1].status(항상 "completed")만으로는 이 정지를
        # 표현할 수 없어 별도 변수로 추적한다.
        review_pending_step_id: str | None = None

        for step_number, step in enumerate(ordered_steps, start=1):
            if step.step_id in step_results:
                # 이미 처리된 step이다(run()의 최초 호출에서는 절대 참이 될
                # 수 없다 - step_results가 빈 dict로 시작하므로. resume()이
                # 미리 채워 넣은 step만 여기서 걸린다) - 다시 실행하지도,
                # completed_steps에 다시 추가하지도 않는다(이미 seed 단계에서
                # 들어가 있다). 11단계 "중복 실행 방지".
                continue

            unmet_deps = [
                dep for dep in step.depends_on if step_results.get(dep) is None or step_results[dep].status != "completed"
            ]
            if unmet_deps:
                # ChiefBrainPlan 검증(chief_brain_plan.py)이 존재하지 않는
                # step_id는 이미 막지만, 순서가 뒤바뀐 depends_on 같은
                # 경우를 대비해 여기서도 방어적으로 확인한다.
                result = self._make_step_result(
                    step,
                    status="blocked",
                    error=f"선행 작업이 아직 완료되지 않았습니다: {unmet_deps}",
                )
                step_results[step.step_id] = result
                completed_steps.append(result)
                break

            needs_approval = step.step_id != bypass_approval_for and (
                step.requires_approval or self._needs_project_checkpoint(plan, step, step_results)
            )
            if needs_approval:
                self._emit_stage(on_stage_changed, f"{step_number}/{total_steps} {step.task_type} 승인 대기")
                if step.requires_approval:
                    result = self._make_step_result(step, status="waiting_for_approval")
                else:
                    # 34단계 - 원본 BrainTaskStep은 절대 수정하지 않는다(계속
                    # requires_approval=False로 남겨둔다). 이번
                    # OrchestrationStepResult 하나에만 requires_approval=True/
                    # approval_reason을 얹어 UI(승인 이유 표시)에 전달한다.
                    result = OrchestrationStepResult(
                        step_id=step.step_id,
                        task_type=step.task_type,
                        status="waiting_for_approval",
                        task_id=None,
                        result=None,
                        error=None,
                        requires_approval=True,
                        approval_reason=step.approval_reason or _PROJECT_CHECKPOINT_REASON,
                    )
                step_results[step.step_id] = result
                completed_steps.append(result)
                break

            if step.task_type == _ANALYSIS_TASK_TYPE:
                if self._analysis_executor is None:
                    result = self._make_step_result(step, status="waiting_for_executor")
                    step_results[step.step_id] = result
                    completed_steps.append(result)
                    break

                context = self._build_execution_context(step, step_results)

                self._emit_stage(on_stage_changed, f"{step_number}/{total_steps} analysis 시작")
                try:
                    review_result = self._analysis_executor.execute(step, context=context)
                except AnalysisExecutionError as exc:
                    result = self._make_step_result(step, status="failed", error=str(exc))
                    step_results[step.step_id] = result
                    completed_steps.append(result)
                    break

                self._emit_stage(on_stage_changed, f"{step_number}/{total_steps} analysis 완료")
                result = self._make_step_result(step, status="completed", result=review_result)
                step_results[step.step_id] = result
                completed_steps.append(result)
                continue

            if step.task_type == _DEVELOPMENT_TASK_TYPE:
                if self._development_executor is None:
                    result = self._make_step_result(step, status="waiting_for_executor")
                    step_results[step.step_id] = result
                    completed_steps.append(result)
                    break

                context = self._build_execution_context(step, step_results)

                self._emit_stage(on_stage_changed, f"{step_number}/{total_steps} development 시작")
                try:
                    dev_result = self._development_executor.execute(step, context=context)
                except DevelopmentExecutionError as exc:
                    result = self._make_step_result(step, status="failed", error=str(exc))
                    step_results[step.step_id] = result
                    completed_steps.append(result)
                    break

                if dev_result.status == "success":
                    self._emit_stage(on_stage_changed, f"{step_number}/{total_steps} development 완료")
                    result = self._make_step_result(step, status="completed", result=dev_result)
                    step_results[step.step_id] = result
                    completed_steps.append(result)
                    if plan.execution_mode == "project":
                        # 36단계 - project 모드는 development가 끝나도 바로
                        # 다음 step으로 넘어가지 않는다(§2). 이 step 자체는
                        # 정말 "completed"다 - 전체 실행만 review 대기로
                        # 멈춘다.
                        review_pending_step_id = step.step_id
                        break
                    continue

                dev_error_text = "; ".join(dev_result.errors) if dev_result.errors else dev_result.summary
                result = self._make_step_result(step, status="failed", error=dev_error_text)
                step_results[step.step_id] = result
                completed_steps.append(result)
                break

            if not self._task_system.worker_registry.has_worker(step.task_type):
                result = self._make_step_result(step, status="waiting_for_executor")
                step_results[step.step_id] = result
                completed_steps.append(result)
                break

            self._emit_stage(on_stage_changed, f"{step_number}/{total_steps} {step.task_type} 시작")
            task = self._task_system.create_task(task_type=step.task_type, title=step.title, goal=step.goal)
            # 46단계 - on_stage_changed를 그대로 on_progress로 재사용한다(§3/§6,
            # 새 이벤트 시스템을 만들지 않는다). Worker(예: ResearchWorker)가
            # 검색 진행 문구를 이 콜백으로 알리면, 기존 stage_changed 전달
            # 경로(orchestration_service.py)를 그대로 타고 MainWindow까지 전달된다.
            executed_task = self._task_system.execute_task(task.task_id, on_progress=on_stage_changed)

            if executed_task.status == "success":
                self._emit_stage(on_stage_changed, f"{step_number}/{total_steps} {step.task_type} 완료")
                result = self._make_step_result(
                    step, status="completed", task_id=executed_task.task_id, result=executed_task.result
                )
                step_results[step.step_id] = result
                completed_steps.append(result)
                continue

            error_text = "; ".join(executed_task.errors) if executed_task.errors else "작업이 실패했습니다."
            result = self._make_step_result(step, status="failed", task_id=executed_task.task_id, error=error_text)
            step_results[step.step_id] = result
            completed_steps.append(result)
            break

        if review_pending_step_id is not None:
            final_status: StepStatus = "waiting_for_review"
            pending_step_id = review_pending_step_id
        else:
            final_status = completed_steps[-1].status if completed_steps else "completed"
            pending_step_id = (
                completed_steps[-1].step_id
                if final_status in ("waiting_for_approval", "waiting_for_executor")
                else None
            )

        return OrchestrationResult(
            status=final_status,
            completed_steps=completed_steps,
            pending_step_id=pending_step_id,
            summary=self._build_summary(final_status, completed_steps),
        )

    @staticmethod
    def _needs_project_checkpoint(
        plan: ChiefBrainPlan, step, step_results: dict[str, OrchestrationStepResult]
    ) -> bool:
        """34단계 - project 모드의 "한방 개발 방지" 안전장치(§3).

        project 모드에서 development step에 도달했는데, 지금까지 실행된
        step 중 requires_approval=True로 멈춘 적이 단 한 번도 없다면(=
        Chief Brain이 스스로 적절한 승인 지점을 두지 않았다면) 이 step
        직전에 강제로 승인 지점을 만든다. task 모드는 항상 False다(task
        모드 기존 동작은 전혀 바꾸지 않는다). 이미 어딘가에서 한 번이라도
        승인을 거쳤다면(Chief Brain이 설계/분석 단계 등에 이미
        requires_approval=True를 뒀거나, 이 development step 자신에
        requires_approval=True가 있어 위쪽 조건에서 이미 걸렸다면) 중복
        승인 지점을 추가하지 않는다.
        """
        if plan.execution_mode != "project":
            return False
        if step.task_type != _DEVELOPMENT_TASK_TYPE:
            return False
        return not any(result.requires_approval for result in step_results.values())

    @staticmethod
    def _build_execution_context(step, step_results: dict[str, OrchestrationStepResult]) -> ExecutionContext:
        """step.depends_on 순서 그대로, "completed"로 끝난 선행 step 결과만 모은다.

        depends_on에 없는 step은 여기 들어올 방법이 없다(step.depends_on만
        순회한다). completed가 아닌 결과는(failed/waiting_for_approval/
        waiting_for_executor/blocked) 방어적으로 한 번 더 걸러낸다 - 정상
        흐름에서는 이미 run()의 unmet_deps 검사에서 걸러지지만, 이 함수만
        따로 재사용될 가능성을 대비한다.
        """
        dependencies: list[StepContext] = []
        for dep_id in step.depends_on:
            dep_result = step_results.get(dep_id)
            if dep_result is None or dep_result.status != "completed":
                continue
            dependencies.append(
                StepContext(step_id=dep_result.step_id, task_type=dep_result.task_type, result=dep_result.result)
            )
        return ExecutionContext(dependencies=dependencies)

    @staticmethod
    def _make_step_result(
        step,
        status: StepStatus,
        task_id: str | None = None,
        result: object | None = None,
        error: str | None = None,
    ) -> OrchestrationStepResult:
        return OrchestrationStepResult(
            step_id=step.step_id,
            task_type=step.task_type,
            status=status,
            task_id=task_id,
            result=result,
            error=error,
            requires_approval=step.requires_approval,
            approval_reason=step.approval_reason,
        )

    @staticmethod
    def _build_summary(status: StepStatus, completed_steps: list[OrchestrationStepResult]) -> str:
        if status == "completed":
            if not completed_steps:
                return "실행할 작업이 없는 계획입니다."
            return f"{len(completed_steps)}개 작업을 모두 완료했습니다."

        last = completed_steps[-1]
        if status == "waiting_for_review":
            return f"'{last.step_id}' 단계 개발이 완료되어 결과 검토가 필요합니다."
        if status == "waiting_for_approval":
            return f"'{last.step_id}' 단계는 승인이 필요해 대기 중입니다."
        if status == "waiting_for_executor":
            return f"'{last.step_id}' 단계(task_type={last.task_type})를 실행할 기능이 아직 없어 대기 중입니다."
        if status == "blocked":
            return f"'{last.step_id}' 단계는 선행 작업이 완료되지 않아 중단되었습니다."
        return f"'{last.step_id}' 단계 실행에 실패했습니다: {last.error}"
