"""MainWindow와 ChiefBrainOrchestrator 사이의 창구.

TaskExecutionService/ResearchReviewService와 동일한 패턴 - research/
development 실행은 시간이 걸릴 수 있는 네트워크/파일 작업이므로 반드시
별도 QThread에서 실행되어 GUI가 멈추지 않는다. MainWindow는
ChiefBrainOrchestrator.run()/resume()을 직접 호출하지 않고 이 서비스를
통해서만 호출한다.

31단계 - stage_changed는 이제 실행이 막 시작될 때("업무 실행 중") 뿐
아니라, ChiefBrainOrchestrator.run()/resume()이 각 step을 실제로
시작/완료할 때마다("N/전체 task_type 시작"/"완료")도 갱신된다.
ChiefBrainOrchestrator는 여전히 PySide6를 전혀 모른다 - run()/resume()에
평범한 Callable[[str], None]을 넘기면, Worker가 자신의 stage_changed
Signal의 emit 메서드를 그 콜백으로 그대로 건네준다(Signal 자체를
Orchestrator에 넘기지 않는다). result_ready/error_occurred와 마찬가지로
QThread.run() 안에서 emit되므로 기존 스레드 안전성 패턴과 동일하다.

29단계 - resume(): screen_observation처럼 승인이 필요했던 step이 UI에서
이미 승인/실행되어 완료된 뒤, 나머지 계획을 이어서 실행할 때 쓴다.
run()과 마찬가지로 QThread에서 실행된다(analysis/development처럼 이어질
step이 네트워크 호출을 할 수 있으므로 GUI를 막으면 안 된다). 두 Worker는
서로 다른 Orchestrator 메서드(run/resume)를 호출할 뿐, 결과를 알리는
방식(result_ready/error_occurred/stage_changed)은 동일해 MainWindow는
어느 쪽에서 온 결과든 같은 핸들러로 처리할 수 있다.

34단계 - resume_project_checkpoint(): project 체크포인트(발판 승인)
이후 그 step을 "처음" 실행하기 위한 별도 창구다. resume()과 구분되는
이유는 ChiefBrainOrchestrator.resume_project_checkpoint()를 그대로
설명한다 - 승인된 step_id만 넘기면 되고, 이미 완성된 결과를 만들어
넘길 필요가 없다. resume()의 시그니처/동작은 전혀 바꾸지 않았다
(screen_observation 경로 무위험).
"""

from PySide6.QtCore import QObject, QThread, Signal

from .chief_brain_orchestrator import ChiefBrainOrchestrator
from .chief_brain_plan import ChiefBrainPlan
from .orchestration_step_result import OrchestrationStepResult

_RUNNING_STAGE_TEXT = "업무 실행 중"


class _OrchestrationWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)
    stage_changed = Signal(str)

    def __init__(self, orchestrator: ChiefBrainOrchestrator, plan: ChiefBrainPlan, parent=None):
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._plan = plan

    def run(self):
        self.stage_changed.emit(_RUNNING_STAGE_TEXT)
        try:
            result = self._orchestrator.run(self._plan, on_stage_changed=self.stage_changed.emit)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class _OrchestrationResumeWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)
    stage_changed = Signal(str)

    def __init__(
        self,
        orchestrator: ChiefBrainOrchestrator,
        plan: ChiefBrainPlan,
        completed_steps: list[OrchestrationStepResult],
        approved_step_result: OrchestrationStepResult,
        parent=None,
    ):
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._plan = plan
        self._completed_steps = completed_steps
        self._approved_step_result = approved_step_result

    def run(self):
        self.stage_changed.emit(_RUNNING_STAGE_TEXT)
        try:
            result = self._orchestrator.resume(
                self._plan, self._completed_steps, self._approved_step_result, on_stage_changed=self.stage_changed.emit
            )
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class _OrchestrationProjectCheckpointResumeWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)
    stage_changed = Signal(str)

    def __init__(
        self,
        orchestrator: ChiefBrainOrchestrator,
        plan: ChiefBrainPlan,
        completed_steps: list[OrchestrationStepResult],
        approved_step_id: str,
        parent=None,
    ):
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._plan = plan
        self._completed_steps = completed_steps
        self._approved_step_id = approved_step_id

    def run(self):
        self.stage_changed.emit(_RUNNING_STAGE_TEXT)
        try:
            result = self._orchestrator.resume_project_checkpoint(
                self._plan, self._completed_steps, self._approved_step_id, on_stage_changed=self.stage_changed.emit
            )
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class OrchestrationService(QObject):
    result_ready = Signal(object)
    error_occurred = Signal(str)
    stage_changed = Signal(str)

    def __init__(self, orchestrator: ChiefBrainOrchestrator, parent=None):
        super().__init__(parent)
        self._orchestrator = orchestrator
        self._worker: QThread | None = None

    def run(self, plan: ChiefBrainPlan):
        self._worker = _OrchestrationWorker(self._orchestrator, plan, parent=self)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.stage_changed.connect(self.stage_changed)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def resume(
        self,
        plan: ChiefBrainPlan,
        completed_steps: list[OrchestrationStepResult],
        approved_step_result: OrchestrationStepResult,
    ):
        self._worker = _OrchestrationResumeWorker(
            self._orchestrator, plan, completed_steps, approved_step_result, parent=self
        )
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.stage_changed.connect(self.stage_changed)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def resume_project_checkpoint(
        self,
        plan: ChiefBrainPlan,
        completed_steps: list[OrchestrationStepResult],
        approved_step_id: str,
    ):
        self._worker = _OrchestrationProjectCheckpointResumeWorker(
            self._orchestrator, plan, completed_steps, approved_step_id, parent=self
        )
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.stage_changed.connect(self.stage_changed)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
