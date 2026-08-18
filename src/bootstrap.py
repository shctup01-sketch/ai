"""main.py가 PySide6/openai/dotenv 등을 import하기 전에 먼저 실행되는 준비 단계.

이 파일은 표준 라이브러리만 사용해야 한다. 아직 필요한 패키지가
설치되지 않은 상태에서도 이 파일 자체는 항상 문제없이 import되어야
안전장치 역할을 할 수 있기 때문이다.
"""

import importlib.util
import os
import subprocess
import sys

_REQUIRED_MODULES = ("PySide6", "openai", "dotenv")


def _project_root() -> str:
    src_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(src_dir)


def _is_missing(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is None


def ensure_dependencies():
    """requirements.txt의 필수 패키지가 설치되어 있는지 확인하고, 없으면 설치한다."""
    missing = [name for name in _REQUIRED_MODULES if _is_missing(name)]
    if not missing:
        return

    requirements_path = os.path.join(_project_root(), "requirements.txt")

    if not os.path.isfile(requirements_path):
        print("필요한 패키지 목록 파일(requirements.txt)을 찾을 수 없습니다.")
        print(f"찾으려 한 위치: {requirements_path}")
        print("프로젝트 폴더 구조를 확인한 뒤 다시 시도해주세요.")
        sys.exit(1)

    print("실행에 필요한 구성 요소가 없어 자동으로 설치합니다. 잠시만 기다려주세요...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", requirements_path]
    )

    if result.returncode != 0:
        print()
        print("필요한 패키지 설치에 실패했습니다.")
        print("인터넷 연결을 확인한 뒤 시작하기.bat를 다시 실행해주세요.")
        sys.exit(1)

    importlib.invalidate_caches()
