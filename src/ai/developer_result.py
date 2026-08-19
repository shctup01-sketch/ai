"""Developer 작업 결과.

project_path/created_files/modified_files는 모델의 자기 보고를 그대로
신뢰하지 않고, 실제로 실행된 파일 작업을 프로그램이 직접 기록한 값으로
채운다 (OpenAIDeveloperProvider 참고).

entry_point는 모델이 "이 파일이 실행 시작 파일이다"라고 보고한 값이다.
어떤 파일이 진입점인지는 프로그램이 대신 판단할 수 없으므로 모델의
보고를 받아들이되, status가 success일 때는 OpenAIDeveloperProvider가
실제 파일 시스템과 대조해 검증한 뒤에만 success를 유지한다.
"""

from typing import Literal

from pydantic import BaseModel


class DeveloperResult(BaseModel):
    status: Literal["success", "failed"]
    summary: str
    project_path: str
    entry_point: str
    created_files: list[str]
    modified_files: list[str]
    errors: list[str]
