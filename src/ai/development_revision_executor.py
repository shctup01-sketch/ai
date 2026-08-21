"""DevelopmentRevisionRequest를 DevelopmentRevisionProvider로 연결하는 어댑터.

AnalysisExecutor/ScreenObservationExecutor와 같은 순수 실행 계층이다 -
QThread/UI(DevelopmentRevisionService/MainWindow)를 전혀 의존하지 않는다.
"""

from .development_revision_plan import DevelopmentRevisionPlan
from .development_revision_provider import DevelopmentRevisionProvider
from .development_revision_request import DevelopmentRevisionRequest


class DevelopmentRevisionExecutionError(Exception):
    """DevelopmentRevisionExecutor가 수정 판단을 완료하지 못했을 때 발생한다.

    DevelopmentRevisionProvider.plan_revision()이 던지는 RuntimeError
    (API Key 누락/인증 실패/네트워크 오류 등)를 가짜 성공으로 둔갑시키지
    않고, 호출자가 명확히 구분해 처리할 수 있는 단일 예외 타입으로
    감싼다. KeyboardInterrupt/SystemExit는 Exception이 아니라 여기서
    잡히지 않고 그대로 전파된다.
    """


class DevelopmentRevisionExecutor:
    """DevelopmentRevisionRequest -> DevelopmentRevisionProvider.plan_revision() 호출만 담당한다."""

    def __init__(self, provider: DevelopmentRevisionProvider):
        self._provider = provider

    def execute(self, request: DevelopmentRevisionRequest) -> DevelopmentRevisionPlan:
        try:
            return self._provider.plan_revision(request)
        except Exception as exc:
            raise DevelopmentRevisionExecutionError(str(exc)) from exc
