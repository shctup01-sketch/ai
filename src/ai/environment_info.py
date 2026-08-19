"""Developer에게 전달할 실제 실행 환경 정보.

사용자가 입력하지 않는다. Studio 자신이 실행 중인 인터프리터를 그대로
조사해서 만든다 (project_venv.ensure_project_venv가 sys.executable을
기준 인터프리터로 프로젝트 venv를 만들기 때문에, Studio의 환경 = 프로젝트
venv의 환경이다).
"""

import platform
import sys

from pydantic import BaseModel


class EnvironmentInfo(BaseModel):
    os_name: str
    python_version: str
    architecture: str
    python_executable: str


def collect_environment_info() -> EnvironmentInfo:
    return EnvironmentInfo(
        os_name=platform.system() or "Unknown",
        python_version=platform.python_version(),
        architecture=platform.architecture()[0],
        python_executable=sys.executable,
    )


def format_environment_info(info: EnvironmentInfo) -> str:
    return (
        "실행 환경:\n"
        f"- OS: {info.os_name}\n"
        f"- Python: {info.python_version}\n"
        f"- Architecture: {info.architecture}\n"
        "- Project environment: isolated .venv\n"
        "- Project venv uses the same Python version as AI Development Studio"
    )
