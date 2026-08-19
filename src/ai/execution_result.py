"""생성 프로젝트 실행 결과.

AI 호출과 무관한 순수 로컬 실행 결과이므로 OpenAI Structured Outputs와는
관계가 없다. ExecutionService가 이 형태로 MainWindow에 결과를 전달한다.

stage는 이 결과가 어느 단계까지 진행된 뒤에 만들어졌는지를 나타낸다.
success/failed 여부와는 별개로, "패키지 설치 실패"만 골라 AI 수정 요청을
제공하려면(일반 실행 오류와 구분) 이 값이 필요하다.
"""

from typing import Literal

from pydantic import BaseModel


class ExecutionResult(BaseModel):
    status: Literal["success", "failed"]
    summary: str
    project_path: str
    entry_point: str
    return_code: int | None
    stdout: str
    stderr: str
    stage: Literal["venv_setup", "package_install", "run"]
