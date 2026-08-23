"""checkpoint 등 UI와 BrainQuestionProvider 사이의 창구(58단계).

chief_brain_service.py/orchestration_service.py와 완전히 동일한 패턴 -
요청은 별도 QThread에서 실행되어 GUI(checkpoint Dialog 포함)가 멈추지
않는다. 기존 orchestration_service/chief_brain_service를 재사용하지
않고 독립 인스턴스로 둔다 - 37/38/45단계에서 이미 확립된 "기존 Service
class를 재사용해야 하지만 기존 wiring과 섞이지 않도록 완전히 분리된
인스턴스를 만든다"는 관례를 그대로 따른다(Qt Signal 교차 오염 방지).
"""

from PySide6.QtCore import QObject, QThread, Signal

from .brain_question_provider import BrainQuestionProvider
from .brain_question_request import BrainQuestionRequest
from .openai_brain_question_provider import OpenAIBrainQuestionProvider


class _BrainQuestionWorker(QThread):
    answer_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, provider: BrainQuestionProvider, request: BrainQuestionRequest, parent=None):
        super().__init__(parent)
        self._provider = provider
        self._request = request

    def run(self):
        try:
            answer = self._provider.answer(self._request)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.answer_ready.emit(answer)


class BrainQuestionService(QObject):
    """checkpoint 등 UI는 이 클래스만 통해 Brain에게 질문한다."""

    answer_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, provider: BrainQuestionProvider | None = None, parent=None):
        super().__init__(parent)
        self._provider = provider or OpenAIBrainQuestionProvider()
        self._worker: _BrainQuestionWorker | None = None

    def ask(self, request: BrainQuestionRequest):
        self._worker = _BrainQuestionWorker(self._provider, request, parent=self)
        self._worker.answer_ready.connect(self.answer_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
