"""Brain의 구조화된 응답 형식.

Brain의 자연어 표현이 달라져도 프로그램이 "이 응답이 확정된 작업
계획인지"를 안정적으로 판단할 수 있도록, 문자열을 검사하는 대신
OpenAI Structured Outputs로 이 형식을 강제한다.
"""

from pydantic import BaseModel


class BrainResponse(BaseModel):
    reply_to_user: str
    is_dev_request: bool
    needs_more_info: bool
    plan_ready: bool
    project_name: str | None
    requirements_summary: str | None
    feature_list: list[str] | None
    task_steps: list[str] | None
