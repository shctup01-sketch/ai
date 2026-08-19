"""패키지 설치 실패에 대한 Developer 수정 요청 입력 데이터.

프로젝트 경로 자체(로컬 파일시스템 경로 문자열)는 Developer에게 아무
의미가 없으므로 보내지 않는다 — Developer는 어차피 list_files/read_file/
write_file 도구를 통해서만 프로젝트에 접근하고, 그 도구들은 이미 올바른
프로젝트 폴더에 고정된 WorkspaceGuard를 통해 동작한다. 대신 Developer가
문제를 판단하는 데 필요한 "내용"만 전달한다.
"""

from pydantic import BaseModel


class DeveloperFixRequest(BaseModel):
    project_name: str
    entry_point: str
    requirements_text: str
    pip_stderr: str
