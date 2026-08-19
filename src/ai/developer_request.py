"""Developer에게 전달할 입력 데이터.

Brain의 reply_to_user 같은 UI 전용 데이터는 Developer에게 필요하지
않으므로 전달하지 않는다.
"""

from pydantic import BaseModel


class DeveloperRequest(BaseModel):
    project_name: str
    requirements_summary: str
    feature_list: list[str]
    task_steps: list[str]
