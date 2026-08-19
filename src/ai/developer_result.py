"""Developer 작업 결과.

project_path/created_files/modified_files는 모델의 자기 보고를 그대로
신뢰하지 않고, 실제로 실행된 파일 작업을 프로그램이 직접 기록한 값으로
채운다 (OpenAIDeveloperProvider 참고).
"""

from typing import Literal

from pydantic import BaseModel


class DeveloperResult(BaseModel):
    status: Literal["success", "failed"]
    summary: str
    project_path: str
    created_files: list[str]
    modified_files: list[str]
    errors: list[str]
