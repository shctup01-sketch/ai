from PySide6.QtCore import QObject, QThread, Signal

from .task_system import TaskSystem


class _TaskExecutionWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, task_system: TaskSystem, task_id: str, parent=None):
        super().__init__(parent)
        self._task_system = task_system
        self._task_id = task_id

    def run(self):
        try:
            result = self._task_system.execute_task(self._task_id)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class TaskExecutionService(QObject):
    """MainWindow와 TaskSystem.execute_task() 사이의 창구.

    BrainService/DeveloperService와 동일한 패턴으로, 요청은 별도 QThread에서
    실행되어 GUI가 멈추지 않는다. 실제 웹 검색(OpenAI Responses API 호출)은
    네트워크 작업이므로 반드시 이 창구를 통해서만 실행한다.
    """

    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, task_system: TaskSystem, parent=None):
        super().__init__(parent)
        self._task_system = task_system
        self._worker: _TaskExecutionWorker | None = None

    def execute_task(self, task_id: str):
        self._worker = _TaskExecutionWorker(self._task_system, task_id, parent=self)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
