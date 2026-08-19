"""Developer가 만지는 모든 파일 작업이 반드시 거쳐야 하는 단일 관문.

Provider가 open()이나 Path.write_text() 등을 직접 호출하지 않고,
반드시 이 모듈의 WorkspaceGuard를 통해서만 workspace 프로젝트 폴더
안의 파일을 읽고 쓰도록 한다. 프로젝트 루트 밖(Studio의 src/, .env,
venv, 배치 파일, 사용자 PC의 다른 경로 등)은 애초에 이 클래스가
알지 못하므로 접근할 방법이 없다.
"""

import re
from pathlib import Path

MAX_FILE_SIZE_BYTES = 1024 * 1024  # 파일 1개당 최대 1MB
MAX_FILES_PER_PROJECT = 100  # 프로젝트당 최대 파일 개수

_FORBIDDEN_NAME_PREFIXES = (".env", ".git")
# 프로젝트 실행 시스템(project_venv.py)이 만들고 사용하는 가상환경 폴더.
# Developer의 파일 도구(list_files/read_file/write_file)는 이 이름의
# 폴더와 그 아래 어떤 경로에도 접근할 수 없다.
_FORBIDDEN_DIR_NAMES = (".venv",)
_WINDOWS_FORBIDDEN_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DRIVE_LETTER_PATTERN = re.compile(r"^[a-zA-Z]:")


class WorkspaceSecurityError(Exception):
    """workspace 경계를 벗어나거나 금지된 접근이 시도되었을 때 발생한다."""


def get_workspace_root() -> Path:
    """<프로젝트 루트>/workspace 를 반환하고, 없으면 만든다."""
    src_dir = Path(__file__).resolve().parent
    project_root = src_dir.parent
    workspace_root = project_root / "workspace"
    workspace_root.mkdir(exist_ok=True)
    return workspace_root


def sanitize_project_name(name: str) -> str:
    cleaned = _WINDOWS_FORBIDDEN_CHARS.sub("_", name).strip().strip(".")
    cleaned = cleaned or "project"
    return cleaned[:80]


def create_project_folder(project_name: str) -> Path:
    """workspace 안에 새 프로젝트 폴더를 만든다. 이미 있으면 덮어쓰지 않고
    _2, _3 처럼 새 이름으로 만든다."""
    workspace_root = get_workspace_root()
    base_name = sanitize_project_name(project_name)

    candidate = workspace_root / base_name
    counter = 2
    while candidate.exists():
        candidate = workspace_root / f"{base_name}_{counter}"
        counter += 1

    candidate.mkdir(parents=True)
    return candidate


class WorkspaceGuard:
    """하나의 Developer 프로젝트 폴더에만 접근할 수 있는 안전한 파일 작업 창구."""

    def __init__(self, project_root: Path):
        self._project_root = project_root.resolve()

    def resolve_path(self, relative_path: str) -> Path:
        if not relative_path or not relative_path.strip():
            raise WorkspaceSecurityError("빈 경로는 사용할 수 없습니다.")

        if Path(relative_path).is_absolute() or _DRIVE_LETTER_PATTERN.match(relative_path):
            raise WorkspaceSecurityError(f"절대경로는 허용되지 않습니다: {relative_path}")

        resolved = (self._project_root / relative_path).resolve()

        try:
            relative_parts = resolved.relative_to(self._project_root).parts
        except ValueError:
            raise WorkspaceSecurityError(
                f"프로젝트 폴더 밖에는 접근할 수 없습니다: {relative_path}"
            ) from None

        if any(part in _FORBIDDEN_DIR_NAMES for part in relative_parts):
            raise WorkspaceSecurityError(
                f"이 경로는 실행 시스템 전용이라 접근할 수 없습니다: {relative_path}"
            )

        if any(resolved.name.startswith(prefix) for prefix in _FORBIDDEN_NAME_PREFIXES):
            raise WorkspaceSecurityError(f"이 이름의 파일/폴더는 사용할 수 없습니다: {resolved.name}")

        return resolved

    def list_files(self) -> list[str]:
        return sorted(
            str(path.relative_to(self._project_root))
            for path in self._project_root.rglob("*")
            if path.is_file()
            and not any(
                part in _FORBIDDEN_DIR_NAMES
                for part in path.relative_to(self._project_root).parts
            )
        )

    def read_file(self, relative_path: str) -> str:
        resolved = self.resolve_path(relative_path)

        if resolved.is_symlink():
            raise WorkspaceSecurityError("심볼릭 링크는 읽을 수 없습니다.")
        if not resolved.exists():
            raise WorkspaceSecurityError(f"파일을 찾을 수 없습니다: {relative_path}")
        if not resolved.is_file():
            raise WorkspaceSecurityError(f"파일이 아닙니다: {relative_path}")

        size = resolved.stat().st_size
        if size > MAX_FILE_SIZE_BYTES:
            raise WorkspaceSecurityError(
                f"파일이 너무 커서 읽을 수 없습니다({size} bytes): {relative_path}"
            )

        return resolved.read_text(encoding="utf-8")

    def write_file(self, relative_path: str, content: str) -> None:
        resolved = self.resolve_path(relative_path)

        if resolved.exists() and resolved.is_symlink():
            raise WorkspaceSecurityError("심볼릭 링크는 만들거나 덮어쓸 수 없습니다.")

        content_bytes = content.encode("utf-8")
        if len(content_bytes) > MAX_FILE_SIZE_BYTES:
            raise WorkspaceSecurityError(
                f"파일 크기 제한({MAX_FILE_SIZE_BYTES} bytes)을 초과합니다: {relative_path}"
            )

        if not resolved.exists():
            current_count = sum(1 for p in self._project_root.rglob("*") if p.is_file())
            if current_count >= MAX_FILES_PER_PROJECT:
                raise WorkspaceSecurityError(
                    f"프로젝트당 최대 파일 개수({MAX_FILES_PER_PROJECT}개)를 초과했습니다."
                )

        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
