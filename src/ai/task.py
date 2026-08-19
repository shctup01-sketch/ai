"""범용 Task System의 가장 기본 데이터 모델.

아직 어떤 기존 코드(MainWindow, Brain, Developer, Execution, PackageFix,
WorkspaceGuard 등)와도 연결되어 있지 않은 독립적인 모델이다. task_type은
Literal/Enum으로 제한하지 않는다 — development, research, business,
file_management, automation 등 앞으로 계속 추가될 작업 종류를 이 파일을
고치지 않고도 받아들이기 위해서다.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Task(BaseModel):
    task_id: str
    task_type: str
    title: str
    goal: str
    status: Literal["planned", "in_progress", "success", "failed"] = "planned"
    current_step: str = ""
    result: object | None = None
    errors: list[str] = Field(default_factory=list)
