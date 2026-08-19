from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from project_runner import run_entry_point
from project_venv import ExecutionStageError, ensure_project_venv, install_requirements

from .execution_result import ExecutionResult


class _ExecutionWorker(QThread):
    result_ready = Signal(object)
    error_occurred = Signal(str)
    stage_changed = Signal(str)

    def __init__(
        self,
        project_path: Path,
        entry_point: Path,
        install_requirements_flag: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._project_path = project_path
        self._entry_point = entry_point
        self._install_requirements = install_requirements_flag

    def run(self):
        try:
            self.stage_changed.emit("가상환경 준비 중")
            venv_python = ensure_project_venv(self._project_path)

            if self._install_requirements:
                self.stage_changed.emit("패키지 설치 중")
                install_requirements(venv_python, self._project_path / "requirements.txt")

            self.stage_changed.emit("실행 중")
            result = run_entry_point(venv_python, self._entry_point, self._project_path)
        except ExecutionStageError as exc:
            result = ExecutionResult(
                status="failed",
                summary=f"{exc.stage} 실패",
                project_path=str(self._project_path),
                entry_point=self._entry_point.name,
                return_code=None,
                stdout="",
                stderr=exc.message,
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
        else:
            self.result_ready.emit(result)


class ExecutionService(QObject):
    """MainWindow와 실행 메커니즘(project_venv/project_runner) 사이의 창구.
    BrainService/DeveloperService와 동일한 패턴으로, 무거운 작업은 별도
    QThread에서 실행되어 GUI가 멈추지 않는다.
    """

    result_ready = Signal(object)
    error_occurred = Signal(str)
    stage_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _ExecutionWorker | None = None

    def run_project(self, project_path: Path, entry_point: Path, install_requirements: bool):
        self._worker = _ExecutionWorker(project_path, entry_point, install_requirements, parent=self)
        self._worker.result_ready.connect(self.result_ready)
        self._worker.error_occurred.connect(self.error_occurred)
        self._worker.stage_changed.connect(self.stage_changed)
        self._worker.finished.connect(self._cleanup_worker)
        self._worker.start()

    def _cleanup_worker(self):
        self._worker = None
