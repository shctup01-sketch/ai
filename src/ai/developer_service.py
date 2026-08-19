from PySide6.QtCore import QObject, QThread, Signal

from .developer_provider import DeveloperProvider
from .developer_request import DeveloperRequest
from .openai_developer_provider import OpenAIDeveloperProvider


class _DeveloperWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, provider: DeveloperProvider, request: DeveloperRequest, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._request = request

    def run(self):
        try:
            result = self._provider.build_project(self._request)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class DeveloperService(QObject):
    """MainWindow와 DeveloperProvider 사이의 창구. BrainService와 동일한 패턴으로,
    요청은 별도 QThread에서 실행되어 GUI가 멈추지 않는다.
    """

    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, provider: DeveloperProvider | None = None, parent=None):
        super().__init__(parent)
        self._provider = provider or OpenAIDeveloperProvider()
        self._worker: _DeveloperWorker | None = None

    def build_project(self, request: DeveloperRequest):
        self._worker = _DeveloperWorker(self._provider, request, parent=self)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
