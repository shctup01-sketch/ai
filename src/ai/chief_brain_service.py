"""ChatPanel과 ChiefBrainProvider 사이의 창구.

BrainService(brain_service.py)와 완전히 동일한 패턴 - 요청은 별도
QThread에서 실행되어 GUI가 멈추지 않는다. BrainService/OpenAIProvider는
이 파일이 대체하지 않는다 - 삭제하지 않고 그대로 둔다(기존 단일 요청
호환 경로의 안전장치로 유지, chief_brain_compat.py 참고).
"""

from PySide6.QtCore import QObject, QThread, Signal

from .chief_brain_provider import ChiefBrainProvider
from .openai_chief_brain_provider import OpenAIChiefBrainProvider


class _ChiefBrainWorker(QThread):
    plan_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, provider: ChiefBrainProvider, messages: list[dict], parent=None):
        super().__init__(parent)
        self._provider = provider
        self._messages = messages

    def run(self):
        try:
            plan = self._provider.plan_work(self._messages)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.plan_ready.emit(plan)


class ChiefBrainService(QObject):
    """ChatPanel과 ChiefBrainProvider 사이의 창구.

    UI는 이 클래스만 통해 Chief Brain을 호출하며, 어떤 회사의 Provider를
    쓰는지는 알지 못한다. 요청은 별도 QThread에서 실행되어 GUI가 멈추지
    않는다.
    """

    plan_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, provider: ChiefBrainProvider | None = None, parent=None):
        super().__init__(parent)
        self._provider = provider or OpenAIChiefBrainProvider()
        self._worker: _ChiefBrainWorker | None = None

    def plan_work(self, messages: list[dict]):
        self._worker = _ChiefBrainWorker(self._provider, messages, parent=self)
        self._worker.plan_ready.connect(self.plan_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
