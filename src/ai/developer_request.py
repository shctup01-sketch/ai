"""Developer에게 전달할 입력 데이터.

Brain의 reply_to_user 같은 UI 전용 데이터는 Developer에게 필요하지
않으므로 전달하지 않는다.

38단계 - existing_project_path: 기본값 None(하위 호환 - 기존 모든
build_project() 호출은 이 필드를 모르고도 그대로 동작한다). 값이
있으면 "새 프로젝트를 만드는 것"이 아니라 "이미 존재하는 이 경로의
프로젝트를 수정하는 것"이라는 뜻이다(OpenAIDeveloperProvider가 이
값으로 새 폴더 생성 여부/지시문을 분기한다) - 수정 요청(project
development 결과 검토 -> 재작업) 흐름에서만 채워진다.
"""

from pydantic import BaseModel


class DeveloperRequest(BaseModel):
    project_name: str
    requirements_summary: str
    feature_list: list[str]
    task_steps: list[str]
    existing_project_path: str | None = None
