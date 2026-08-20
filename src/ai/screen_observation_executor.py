"""BrainTaskStep(task_type="screen_observation")을 ScreenObservationProvider로 연결하는 어댑터.

AnalysisExecutor/DevelopmentExecutor와 같은 순수 실행 계층이다 - QThread/
UI(ScreenObservationService/MainWindow)를 전혀 의존하지 않는다.

이 실행기는 "이미 승인되고, 이미 캡처된" 이미지(data_url 문자열)를
그대로 받는다 - 승인 여부 판단이나 화면 캡처 자체는 이 파일의 책임이
아니다(ChiefBrainOrchestrator/MainWindow가 승인을 확인한 뒤에만 이
execute()를 호출한다는 기존 원칙과 동일하게, AnalysisExecutor/
DevelopmentExecutor도 승인 여부를 스스로 판단하지 않는다).
"""

from .brain_task_step import BrainTaskStep
from .screen_observation_provider import ScreenObservationProvider
from .screen_observation_request import ScreenObservationRequest
from .screen_observation_result import ScreenObservationResult


class ScreenObservationExecutionError(Exception):
    """ScreenObservationExecutor가 화면 분석을 완료하지 못했을 때 발생한다.

    ScreenObservationProvider.observe()가 던지는 RuntimeError(API Key
    누락/인증 실패/네트워크 오류 등)를 가짜 success로 둔갑시키지 않고,
    호출자가 명확히 구분해 처리할 수 있는 단일 예외 타입으로 감싼다.
    KeyboardInterrupt/SystemExit는 Exception이 아니라 여기서 잡히지 않고
    그대로 전파된다.
    """


class ScreenObservationExecutor:
    """BrainTaskStep + 캡처된 이미지 -> ScreenObservationRequest 변환 후 Provider.observe()를 호출한다."""

    def __init__(self, provider: ScreenObservationProvider):
        self._provider = provider

    def execute(self, step: BrainTaskStep, plan_objective: str, image_data_url: str) -> ScreenObservationResult:
        request = ScreenObservationRequest(
            objective=plan_objective,
            step_goal=step.goal,
            approval_reason=step.approval_reason or "",
            image_data_url=image_data_url,
        )
        try:
            return self._provider.observe(request)
        except Exception as exc:
            raise ScreenObservationExecutionError(str(exc)) from exc
