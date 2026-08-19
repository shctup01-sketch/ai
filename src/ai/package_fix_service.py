from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from .developer_fix_request import DeveloperFixRequest
from .openai_developer_provider import OpenAIDeveloperProvider


class _PackageFixWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(
        self,
        provider: OpenAIDeveloperProvider,
        project_path: Path,
        request: DeveloperFixRequest,
        parent=None,
    ):
        super().__init__(parent)
        self._provider = provider
        self._project_path = project_path
        self._request = request

    def run(self):
        try:
            result = self._provider.fix_packages(self._project_path, self._request)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class PackageFixService(QObject):
    """MainWindow와 OpenAIDeveloperProvider.fix_packages() 사이의 창구.
    DeveloperService와 동일한 패턴으로, 요청은 별도 QThread에서 실행되어
    GUI가 멈추지 않는다.
    """

    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, provider: OpenAIDeveloperProvider | None = None, parent=None):
        super().__init__(parent)
        self._provider = provider or OpenAIDeveloperProvider()
        self._worker: _PackageFixWorker | None = None

    def fix_packages(self, project_path: Path, request: DeveloperFixRequest):
        self._worker = _PackageFixWorker(self._provider, project_path, request, parent=self)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
