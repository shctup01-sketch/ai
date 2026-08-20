"""MainWindow와 ScreenObservationExecutor 사이의 창구.

ChiefBrainService/ResearchReviewService와 동일한 패턴 - Provider 호출은
네트워크 요청이라 시간이 걸릴 수 있으므로 반드시 별도 QThread에서
실행되어 GUI가 멈추지 않는다.

이 서비스는 화면을 캡처하지 않는다 - image_data_url은 이미
MainWindow(UI 스레드)에서 screen_capture.py + 기존 이미지 인코딩
파이프라인을 거쳐 만들어진 순수 문자열이어야 한다. QImage/QPixmap 같은
Qt 객체를 이 스레드 경계 너머로 넘기지 않는다.
"""

from PySide6.QtCore import QObject, QThread, Signal

from .brain_task_step import BrainTaskStep
from .screen_observation_executor import ScreenObservationExecutor


class _ScreenObservationWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(
        self,
        executor: ScreenObservationExecutor,
        step: BrainTaskStep,
        plan_objective: str,
        image_data_url: str,
        parent=None,
    ):
        super().__init__(parent)
        self._executor = executor
        self._step = step
        self._plan_objective = plan_objective
        self._image_data_url = image_data_url

    def run(self):
        try:
            result = self._executor.execute(self._step, self._plan_objective, self._image_data_url)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class ScreenObservationService(QObject):
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, executor: ScreenObservationExecutor, parent=None):
        super().__init__(parent)
        self._executor = executor
        self._worker: _ScreenObservationWorker | None = None

    def observe(self, step: BrainTaskStep, plan_objective: str, image_data_url: str):
        self._worker = _ScreenObservationWorker(self._executor, step, plan_objective, image_data_url, parent=self)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
