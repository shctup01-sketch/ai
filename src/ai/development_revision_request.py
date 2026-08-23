"""사용자의 "수정 요청"을 Chief Brain의 수정 판단으로 넘길 때 쓰는 입력 데이터.

38단계 - project development 결과 검토(waiting_for_review) 화면에서
"수정 요청"을 선택했을 때 채워진다. 모든 필드는 이미 존재하는 실제
객체(BrainTaskStep/DeveloperResult/ScreenObservationResult/ChiefBrainPlan)
에서 가져온 값만 담는다 - 없는 정보를 지어내지 않는다(37단계 원칙과
동일). screen_observation_summary는 사용자가 37단계 "실행해서 확인"을
거쳐 화면 분석까지 마친 경우에만 채워지고, 그렇지 않으면 None이다
(§14 - 없으면 없는 대로 안전하게 동작해야 한다).

57단계 - product_context(기본값 "")는 프로젝트의 승인된 장기 제품
기준(project_product_context.py) 요약이다. project_objective(한 줄
자유 텍스트)만으로는 실제 GameBlock 프로젝트에서 Analysis가 "승인된
구조의 구체적인 명세가 제공되지 않았다"고 판단한 문제가 그대로
재현되므로, "수정 요청" 판단(Brain)에도 같은 값을 함께 전달한다.
"""

from pydantic import BaseModel


class DevelopmentRevisionRequest(BaseModel):
    project_objective: str
    current_step_title: str
    current_step_goal: str
    developer_summary: str
    created_files: list[str]
    modified_files: list[str]
    user_revision_request: str
    screen_observation_summary: str | None
    product_context: str = ""
