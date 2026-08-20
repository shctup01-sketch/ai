"""MainWindow와 ResearchReviewerProvider 사이의 창구.

TaskExecutionService/DeveloperService와 동일한 패턴으로, 요청은 별도
QThread에서 실행되어 GUI가 멈추지 않는다. 실제 분석(OpenAI Responses API
호출)은 네트워크 작업이므로 반드시 이 창구를 통해서만 실행한다 -
MainWindow가 ResearchReviewerProvider를 직접 호출하지 않는다.
"""

from PySide6.QtCore import QObject, QThread, Signal

from .research_review_request import ResearchReviewRequest
from .research_reviewer_provider import ResearchReviewerProvider


class _ResearchReviewWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, provider: ResearchReviewerProvider, request: ResearchReviewRequest, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._request = request

    def run(self):
        try:
            result = self._provider.review(self._request)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class ResearchReviewService(QObject):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, provider: ResearchReviewerProvider, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._worker: _ResearchReviewWorker | None = None

    def review(self, request: ResearchReviewRequest):
        self._worker = _ResearchReviewWorker(self._provider, request, parent=self)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
