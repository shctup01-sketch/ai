"""BrainTaskStep을 기존 Developer 실행 경로(DeveloperProvider)로 연결하는 어댑터.

DeveloperService(QThread 기반 UI 서비스 계층)를 직접 의존하지 않는다 -
이 파일은 순수 실행 계층이라 QObject/QThread/UI를 전혀 모른다. 새 개발
AI를 만들지 않고, 기존에 이미 검증된 DeveloperProvider 계약(추상
인터페이스, developer_provider.py)을 그대로 재사용해
OpenAIDeveloperProvider.build_project()를 그대로 호출한다.

이번 v1은 step.title/step.goal만으로 DeveloperRequest를 만든다 -
research 등 이전 step의 결과를 여기 자동으로 섞어 넣지 않는다(그건
다음 단계의 Result Context가 할 일이다). feature_list/task_steps는
BrainTaskStep에 대응하는 정보가 없으므로 빈 리스트로 둔다 -
chief_brain_compat.py의 기존 BrainResponse 변환에서도 동일하게
처리한 전례를 그대로 따른다.

프로그램 실행(entry_point 확인/venv/requirements 설치/실제 실행)은 이
파일의 책임이 아니다 - "프로젝트 코드 생성 완료"까지만 담당한다.
"""

from .brain_task_step import BrainTaskStep
from .developer_provider import DeveloperProvider
from .developer_request import DeveloperRequest
from .developer_result import DeveloperResult


class DevelopmentExecutionError(Exception):
    """DevelopmentExecutor가 Developer 실행을 완료하지 못했을 때 발생한다.

    DeveloperProvider.build_project()가 던지는 RuntimeError(API Key
    누락/인증 실패/네트워크 오류 등)를 가짜 success로 둔갑시키지 않고,
    호출자(Orchestrator)가 명확히 구분해 처리할 수 있는 단일 예외
    타입으로 감싼다. KeyboardInterrupt/SystemExit는 Exception이 아니라
    여기서 잡히지 않고 그대로 전파된다.
    """


class DevelopmentExecutor:
    """BrainTaskStep -> DeveloperRequest 변환 후 DeveloperProvider.build_project()를 호출한다."""

    def __init__(self, developer_provider: DeveloperProvider):
        self._developer_provider = developer_provider

    def execute(self, step: BrainTaskStep) -> DeveloperResult:
        request = self._build_request(step)
        try:
            return self._developer_provider.build_project(request)
        except Exception as exc:
            raise DevelopmentExecutionError(str(exc)) from exc

    @staticmethod
    def _build_request(step: BrainTaskStep) -> DeveloperRequest:
        return DeveloperRequest(
            project_name=step.title,
            requirements_summary=step.goal,
            feature_list=[],
            task_steps=[],
        )
