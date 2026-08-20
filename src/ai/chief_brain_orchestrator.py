"""ChiefBrainPlan을 실제 TaskSystem 실행으로 연결하는 첫 Orchestrator(v1).

이 파일은 TaskSystem을 생성자에서 외부 주입받을 뿐, 내부에서 새로
만들지 않는다. OpenAI client/Provider를 전혀 알지 못하고(이 파일에는
OpenAI 관련 import가 없다), MainWindow/ChatPanel/BrainService/
DeveloperService/ExecutionService/PackageFixService 무엇과도 연결되어
있지 않다 - 이번 단계는 "계획을 실제로 실행할 수 있는 엔진"까지만
만들고, UI 연결은 다음 단계로 미룬다.

v1 범위(중요, 의도적인 제약):
- 현재 TaskSystem에 실제로 등록된 Worker는 research 하나뿐이다.
  등록되지 않은 task_type(development 포함)을 억지로 아무 Worker에게나
  보내지 않는다 - WorkerRegistry.has_worker()로 먼저 확인하고, 없으면
  "waiting_for_executor"로 멈춘다. development를 기존 DeveloperService에
  연결하는 것은 다음 단계의 일이다.
- requires_approval=True인 step은 자동 실행하지 않는다. 이 안에서
  "승인됐다"는 값을 스스로 만들어내지 않는다(approved=True 같은 것을
  하드코딩하지 않는다) - 그 UI/재개(resume) 흐름은 다음 단계의 일이다.
- research 성공 결과를 development 등 다음 step의 goal에 자동으로
  집어넣는 일도 하지 않는다(Result Context 설계는 다음 단계).
- 어떤 step이든 order 순서상 이후 step은, 그 앞의 step이 정확히
  "completed"로 끝난 경우에만 진행한다. 승인 대기/실행기 없음/실패/
  (방어적으로 확인하는) 선행 작업 미완료 중 어떤 상태로든 멈추면 그
  즉시 전체 실행을 중단한다 - 이후 step은 아예 처리를 시도하지 않는다.
"""

from .chief_brain_plan import ChiefBrainPlan
from .orchestration_result import OrchestrationResult
from .orchestration_step_result import OrchestrationStepResult, StepStatus
from .task_system import TaskSystem


class ChiefBrainOrchestrator:
    """ChiefBrainPlan.steps를 order 순서대로 처리해 TaskSystem으로 실행한다."""

    def __init__(self, task_system: TaskSystem):
        self._task_system = task_system

    def run(self, plan: ChiefBrainPlan) -> OrchestrationResult:
        if not plan.steps:
            return OrchestrationResult(
                status="completed",
                completed_steps=[],
                pending_step_id=None,
                summary="실행할 작업이 없는 계획입니다.",
            )

        # plan.steps를 정렬만 할 뿐 원본 리스트/step 객체는 어디서도
        # 수정하지 않는다(sorted()는 새 리스트를 반환한다).
        ordered_steps = sorted(plan.steps, key=lambda step: step.order)

        step_results: dict[str, OrchestrationStepResult] = {}
        completed_steps: list[OrchestrationStepResult] = []

        for step in ordered_steps:
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

            if step.requires_approval:
                result = self._make_step_result(step, status="waiting_for_approval")
                step_results[step.step_id] = result
                completed_steps.append(result)
                break

            if not self._task_system.worker_registry.has_worker(step.task_type):
                result = self._make_step_result(step, status="waiting_for_executor")
                step_results[step.step_id] = result
                completed_steps.append(result)
                break

            task = self._task_system.create_task(task_type=step.task_type, title=step.title, goal=step.goal)
            executed_task = self._task_system.execute_task(task.task_id)

            if executed_task.status == "success":
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

        final_status: StepStatus = completed_steps[-1].status if completed_steps else "completed"
        pending_step_id = (
            completed_steps[-1].step_id if final_status in ("waiting_for_approval", "waiting_for_executor") else None
        )

        return OrchestrationResult(
            status=final_status,
            completed_steps=completed_steps,
            pending_step_id=pending_step_id,
            summary=self._build_summary(final_status, completed_steps),
        )

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
        if status == "waiting_for_approval":
            return f"'{last.step_id}' 단계는 승인이 필요해 대기 중입니다."
        if status == "waiting_for_executor":
            return f"'{last.step_id}' 단계(task_type={last.task_type})를 실행할 기능이 아직 없어 대기 중입니다."
        if status == "blocked":
            return f"'{last.step_id}' 단계는 선행 작업이 완료되지 않아 중단되었습니다."
        return f"'{last.step_id}' 단계 실행에 실패했습니다: {last.error}"
