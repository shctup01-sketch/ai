"""생성된 프로젝트의 실행 시작 파일(entry_point)을 프로젝트 전용 가상환경에서
실행한다.

어떤 파일이 실행 시작 파일인지는 Developer가 DeveloperResult.entry_point로
명시적으로 보고한다 (main.py 등 특정 이름을 고정 탐색하지 않는다).
이 모듈은 그 보고값을 실제 파일 시스템과 대조해 안전하게 검증하는
역할만 한다. exe/bat/cmd/PowerShell 등 다른 실행 방식은 다루지 않는다.
"""

import subprocess
from pathlib import Path

from ai.execution_result import ExecutionResult
from workspace_guard import WorkspaceGuard, WorkspaceSecurityError

LIVENESS_CHECK_SECONDS = 3
OUTPUT_CHAR_LIMIT = 4000


class EntryPointError(Exception):
    """entry_point가 안전하지 않거나 실제로 존재하지 않을 때 발생한다."""


def resolve_entry_point(project_path: Path, entry_point: str) -> Path:
    """entry_point 상대경로를 검증하고 실행 가능한 절대경로를 돌려준다.

    WorkspaceGuard.resolve_path()의 경로 안전 검증(절대경로 금지, ../ 탈출
    금지, .venv 접근 금지 등)을 그대로 재사용한 뒤, 실행에 필요한 추가
    조건(존재 여부, 일반 파일 여부, 심볼릭 링크 금지, .py 확장자)을 검사한다.
    """
    guard = WorkspaceGuard(project_path)

    try:
        resolved = guard.resolve_path(entry_point)
    except WorkspaceSecurityError as exc:
        raise EntryPointError(str(exc)) from exc

    # resolve_path()는 내부적으로 Path.resolve()를 거치면서 심볼릭 링크를
    # 이미 완전히 따라간 최종 경로를 돌려준다. 그 최종 경로에 대고
    # is_symlink()를 확인하면 항상 False이므로 (더 이상 링크가 아니라
    # 링크가 가리키던 실제 파일이므로) 무의미하다. 링크 여부는 아직
    # 해석하기 전의 원본 경로(project_path / entry_point)에서 확인해야 한다.
    if (project_path / entry_point).is_symlink():
        raise EntryPointError(f"심볼릭 링크는 실행할 수 없습니다: {entry_point}")

    if resolved.suffix != ".py":
        raise EntryPointError(f"Python(.py) 파일만 실행할 수 있습니다: {entry_point}")

    if not resolved.exists():
        raise EntryPointError(f"실행 파일을 찾을 수 없습니다: {entry_point}")

    if not resolved.is_file():
        raise EntryPointError(f"파일이 아닙니다: {entry_point}")

    return resolved


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
            stage="run",
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
            stage="run",
        )

    return ExecutionResult(
        status="failed",
        summary="프로그램 실행 중 오류가 발생했습니다.",
        project_path=str(project_path),
        entry_point=entry_point.name,
        return_code=process.returncode,
        stdout=_truncate(stdout or ""),
        stderr=_truncate(stderr or ""),
        stage="run",
    )
