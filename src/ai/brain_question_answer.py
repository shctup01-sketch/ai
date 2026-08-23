"""Brain 질문(58단계)에 대한 구조화된 응답 형식.

brain_response.py의 기존 교훈(§ "필드 선언 순서가 곧 모델이 값을 채우는
순서다")을 그대로 따른다 - 분류 필드(is_change_request)를 자연어
답변(answer)보다 앞에 둬서, 모델이 답변부터 다 쓴 뒤 뒤늦게 분류를
끼워 맞추지 않게 한다.

is_change_request는 58단계 §8의 "질문/변경 의도 구분" 최소 기반이다.
True라고 해서 이 자리에서 계획/코드/persistent state를 실제로 바꾸지
않는다 - 이 값을 읽는 쪽(main_window.py)도 승인 없이는 아무것도
바꾸지 않는다. 이 필드는 향후 안전한 계획 변경 흐름으로 연결하기 위한
신호일 뿐이다.
"""

from pydantic import BaseModel


class BrainQuestionAnswer(BaseModel):
    is_change_request: bool
    answer: str
