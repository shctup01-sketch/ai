"""ScreenObservationProvider.observe()에 넘길 요청 데이터.

ResearchReviewRequest(research_review_request.py)와 동일한 설계 - 이미
승인/캡처가 끝난 뒤의 "순수 데이터"만 담는다. QImage/QPixmap 같은 Qt
객체나 파일 경로는 여기 없다 - image_data_url은 이미 chat_panel.py/
screen_capture.py 파이프라인을 거쳐 만들어진 순수 문자열
("data:image/png;base64,...")이다.
"""

from pydantic import BaseModel


class ScreenObservationRequest(BaseModel):
    objective: str
    step_goal: str
    approval_reason: str
    image_data_url: str
