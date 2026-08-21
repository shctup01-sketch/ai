"""MainWindow와 DevelopmentRevisionExecutor 사이의 창구.

ScreenObservationService/AnalysisService와 동일한 패턴 - Provider 호출은
네트워크 요청이라 시간이 걸릴 수 있으므로 반드시 별도 QThread에서
실행되어 GUI가 멈추지 않는다.
"""

from PySide6.QtCore import QObject, QThread, Signal

from .development_revision_executor import DevelopmentRevisionExecutor
from .development_revision_request import DevelopmentRevisionRequest


class _DevelopmentRevisionWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(
        self,
        executor: DevelopmentRevisionExecutor,
        request: DevelopmentRevisionRequest,
        parent=None,
    ):
        super().__init__(parent)
        self._executor = executor
        self._request = request

    def run(self):
        try:
            result = self._executor.execute(self._request)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class DevelopmentRevisionService(QObject):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, executor: DevelopmentRevisionExecutor, parent=None):
        super().__init__(parent)
        self._executor = executor
        self._worker: _DevelopmentRevisionWorker | None = None

    def plan_revision(self, request: DevelopmentRevisionRequest):
        self._worker = _DevelopmentRevisionWorker(self._executor, request, parent=self)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
