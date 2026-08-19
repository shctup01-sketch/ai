"""생성 프로젝트 실행 결과.

AI 호출과 무관한 순수 로컬 실행 결과이므로 OpenAI Structured Outputs와는
관계가 없다. ExecutionService가 이 형태로 MainWindow에 결과를 전달한다.
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
