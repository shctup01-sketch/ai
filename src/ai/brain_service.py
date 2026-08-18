from PySide6.QtCore import QObject, QThread, Signal

from .openai_provider import OpenAIProvider
from .provider import AIProvider


class _BrainWorker(QThread):
    response_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, provider: AIProvider, messages: list[dict], parent=None):
        super().__init__(parent)
        self._provider = provider
        self._messages = messages

    def run(self):
        try:
            response = self._provider.send_message(self._messages)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.response_ready.emit(response)


class BrainService(QObject):
    """ChatPanel과 AIProvider 사이의 창구.

    UI는 이 클래스만 통해 AI를 호출하며, 어떤 회사의 Provider를 쓰는지는
    알지 못한다. 요청은 별도 QThread에서 실행되어 GUI가 멈추지 않는다.
    """

    response_ready = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, provider: AIProvider | None = None, parent=None):
        super().__init__(parent)
        self._provider = provider or OpenAIProvider()
        self._worker: _BrainWorker | None = None

    def send_message(self, messages: list[dict]):
        self._worker = _BrainWorker(self._provider, messages, parent=self)
        self._worker.response_ready.connect(self.response_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
