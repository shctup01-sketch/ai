"""MainWindow와 ChiefBrainOrchestrator 사이의 창구.

TaskExecutionService/ResearchReviewService와 동일한 패턴 - research/
development 실행은 시간이 걸릴 수 있는 네트워크/파일 작업이므로 반드시
별도 QThread에서 실행되어 GUI가 멈추지 않는다. MainWindow는
ChiefBrainOrchestrator.run()을 직접 호출하지 않고 이 서비스를 통해서만
호출한다.

stage_changed는 Orchestrator 내부 진행 단계를 세밀하게 보고하지 않는다
(ChiefBrainOrchestrator.run()은 단계별 콜백 없이 한 번에 실행되는 동기
메서드이고, 이 라운드에서 그 구조를 바꾸지 않는다) - 실행이 막 시작될
때 한 번만 "업무 실행 중"을 알려 WORK STATUS를 갱신할 수 있게 한다.
"""

from PySide6.QtCore import QObject, QThread, Signal

from .chief_brain_orchestrator import ChiefBrainOrchestrator
from .chief_brain_plan import ChiefBrainPlan

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
            result = self._orchestrator.run(self._plan)
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
        self._worker: _OrchestrationWorker | None = None

    def run(self, plan: ChiefBrainPlan):
        self._worker = _OrchestrationWorker(self._orchestrator, plan, parent=self)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.stage_changed.connect(self.stage_changed)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
