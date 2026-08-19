"""프로젝트 전용 가상환경 생성과 패키지 설치.

AI Development Studio 본체의 venv와는 완전히 분리된, 생성된 프로젝트만을
위한 독립 가상환경을 다룬다. 이 모듈의 어떤 함수도 Studio 본체 venv에는
손을 대지 않는다.
"""

import re
import subprocess
import sys
from pathlib import Path

VENV_DIR_NAME = ".venv"
INSTALL_TIMEOUT_SECONDS = 180

_DANGEROUS_SUBSTRINGS = (
    "http://",
    "https://",
    "git+",
    "file:",
    "--index-url",
    "--extra-index-url",
)
_DANGEROUS_PREFIXES = ("-i", "-e", "--editable")

# 일반적인 PyPI 패키지 지정(이름[extras]비교연산자버전, 환경 마커 포함)만 허용한다.
_SAFE_REQUIREMENT_LINE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(\[[A-Za-z0-9,_-]+\])?"
    r"\s*"
    r"([=<>!~]=?\s*[A-Za-z0-9.*+!-]+)?"
    r"(\s*,\s*[=<>!~]=?\s*[A-Za-z0-9.*+!-]+)*"
    r"(\s*;.*)?$"
)

_ERROR_MESSAGE_LIMIT = 2000


class ExecutionStageError(Exception):
    """venv 생성 또는 패키지 설치처럼, 실행 준비 단계에서 예상 가능한 실패."""

    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage
        self.message = _truncate(message)


def _truncate(text: str) -> str:
    if len(text) <= _ERROR_MESSAGE_LIMIT:
        return text
    return text[:_ERROR_MESSAGE_LIMIT] + "\n... (이하 생략)"


def get_venv_python(project_path: Path) -> Path:
    venv_dir = project_path / VENV_DIR_NAME
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_project_venv(project_path: Path) -> Path:
    """프로젝트 전용 가상환경이 없으면 만들고, python 실행 파일 경로를 돌려준다.

    Studio 자신을 실행 중인 인터프리터(sys.executable)를 기준 인터프리터로
    사용한다. venv 모듈은 기존 venv 안에서 실행되더라도 site-packages가
    빈 새 가상환경을 만들기 때문에, Studio에 설치된 패키지가 새 가상환경으로
    섞여 들어가지 않는다. Studio venv 자체에는 어떤 패키지도 설치하지 않는다.
    """
    venv_python = get_venv_python(project_path)
    if venv_python.exists():
        return venv_python

    venv_dir = project_path / VENV_DIR_NAME
    try:
        result = subprocess.run(
            [sys.executable, "-m", "venv", str(venv_dir)],
            shell=False,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExecutionStageError("가상환경 생성", "시간 초과") from exc

    if result.returncode != 0 or not venv_python.exists():
        raise ExecutionStageError("가상환경 생성", result.stderr or "알 수 없는 오류")

    return venv_python


def parse_requirements(text: str) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)
    return lines


def find_unsafe_requirements(lines: list[str]) -> list[str]:
    """일반 PyPI 패키지 지정이 아닌, 위험할 수 있는 줄 목록을 돌려준다."""
    unsafe = []
    for line in lines:
        lower = line.lower()
        if any(token in lower for token in _DANGEROUS_SUBSTRINGS):
            unsafe.append(line)
            continue
        if any(lower.startswith(prefix) for prefix in _DANGEROUS_PREFIXES):
            unsafe.append(line)
            continue
        if "/" in line or "\\" in line:
            unsafe.append(line)
            continue
        if not _SAFE_REQUIREMENT_LINE.match(line):
            unsafe.append(line)
    return unsafe


def install_requirements(venv_python: Path, requirements_path: Path) -> None:
    """프로젝트 전용 venv의 python으로만 requirements.txt를 설치한다."""
    try:
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "--no-input", "-r", str(requirements_path)],
            shell=False,
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExecutionStageError("패키지 설치", "시간 초과") from exc

    if result.returncode != 0:
        raise ExecutionStageError("패키지 설치", result.stderr or "알 수 없는 오류")
