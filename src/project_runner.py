"""생성된 프로젝트의 진입점(main.py)을 프로젝트 전용 가상환경에서 실행한다.

v0.1에서는 프로젝트 루트의 main.py 하나만 실행 대상으로 허용한다.
exe/bat/cmd/PowerShell 등 다른 실행 방식은 다루지 않는다.
"""

import subprocess
from pathlib import Path

from ai.execution_result import ExecutionResult

ENTRY_POINT_FILENAME = "main.py"
LIVENESS_CHECK_SECONDS = 3
OUTPUT_CHAR_LIMIT = 4000


def find_entry_point(project_path: Path) -> Path | None:
    candidate = project_path / ENTRY_POINT_FILENAME
    return candidate if candidate.is_file() else None


def _truncate(text: str) -> str:
    if len(text) <= OUTPUT_CHAR_LIMIT:
        return text
    return text[:OUTPUT_CHAR_LIMIT] + "\n... (이하 생략)"


def run_entry_point(venv_python: Path, entry_point: Path, project_path: Path) -> ExecutionResult:
    """entry_point를 실행하고, 정해진 시간 안의 생존 여부로 성공/실패를 판단한다.

    GUI/게임 프로그램처럼 계속 실행되는 경우를 위해, 정해진 시간이 지나도
    살아 있으면 강제 종료하지 않고 성공으로 처리한다.
    """
    process = subprocess.Popen(
        [str(venv_python), str(entry_point)],
        cwd=str(project_path),
        shell=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        stdout, stderr = process.communicate(timeout=LIVENESS_CHECK_SECONDS)
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            status="success",
            summary="프로그램이 실행되어 계속 동작 중입니다.",
            project_path=str(project_path),
            entry_point=entry_point.name,
            return_code=None,
            stdout="",
            stderr="",
        )

    if process.returncode == 0:
        return ExecutionResult(
            status="success",
            summary="프로그램이 정상적으로 종료되었습니다.",
            project_path=str(project_path),
            entry_point=entry_point.name,
            return_code=process.returncode,
            stdout=_truncate(stdout or ""),
            stderr=_truncate(stderr or ""),
        )

    return ExecutionResult(
        status="failed",
        summary="프로그램 실행 중 오류가 발생했습니다.",
        project_path=str(project_path),
        entry_point=entry_point.name,
        return_code=process.returncode,
        stdout=_truncate(stdout or ""),
        stderr=_truncate(stderr or ""),
    )
