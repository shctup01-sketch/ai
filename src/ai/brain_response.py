"""Brain의 구조화된 응답 형식.

Brain의 자연어 표현이 달라져도 프로그램이 "이 응답이 확정된 작업
계획인지"를 안정적으로 판단할 수 있도록, 문자열을 검사하는 대신
OpenAI Structured Outputs로 이 형식을 강제한다.

필드 선언 순서가 곧 모델이 값을 채우는 순서다(OpenAI Structured
Outputs는 JSON schema의 property 순서대로 토큰을 생성한다). 그래서
분류 필드(task_type/is_dev_request/needs_more_info/plan_ready)를
reply_to_user보다 앞에 둔다 - reply_to_user가 먼저 오면 모델이 분류를
정하기도 전에 답변부터 작성하게 되어, 그 답변이 이미 "일반 대화형
직접 답변"으로 굳어진 뒤에야 뒤늦게 task_type이 채워지는 문제가
생긴다(실기에서 반복 관찰된 오분류의 실제 원인).

task_type은 Literal로 development/research/general 세 값만 허용한다 -
문자열 자유 서술이면 모델이 스키마 차원의 제약 없이 아무 문자열이나
쓸 수 있어 분류가 프롬프트 설명에만 의존하게 된다. 다른 값이 필요해지면
이 Literal에 값을 추가한다. project_name 등 기존 개발 전용 필드는
task_type=research용으로 재사용하지 않고, research_title/research_goal을
별도로 둔다.
"""

from typing import Literal

from pydantic import BaseModel


class BrainResponse(BaseModel):
    task_type: Literal["development", "research", "general"]
    is_dev_request: bool
    needs_more_info: bool
    plan_ready: bool
    reply_to_user: str
    project_name: str | None
    requirements_summary: str | None
    feature_list: list[str] | None
    task_steps: list[str] | None
    research_title: str | None
    research_goal: str | None
