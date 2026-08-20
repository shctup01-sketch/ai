"""사용자가 채팅에 붙여넣은 이미지를 OpenAI Responses API가 받는 content item
형태로 변환하는 순수 로직.

PySide6(QImage/QPixmap 등)에 전혀 의존하지 않는다 - 클립보드에서 이미지를
꺼내고 리사이즈/PNG 인코딩하는 것은 Qt가 필요한 chat_panel.py의 몫이고,
이 파일은 "이미 PNG로 인코딩된 bytes" 또는 "이미 만들어진 data URL 문자열"
같은 순수 Python 데이터만 다룬다. 그래야 PySide6.QtGui를 import할 수 없는
환경(이 저장소의 Linux 테스트 환경 등)에서도 이 파일의 로직을 실제로
실행해 테스트할 수 있다.

content item 형태(input_text/input_image)는 추측하지 않고 설치된 openai
SDK(3.2.0)의 ResponseInputTextParam/ResponseInputImageParam 타입 정의를
직접 확인해서 맞췄다. client.responses.parse(input=messages)의 messages는
{"role": ..., "content": str | list[input_text/input_image 항목]} 형태를
그대로 받아들이므로, 여기서 만든 dict를 그대로 ChatPanel의 self._history에
넣으면 ChiefBrainService/OpenAIChiefBrainProvider는 한 줄도 바꾸지 않아도
이미지를 그대로 전달한다(둘 다 messages를 그 형태 그대로 통과시키기만
한다).
"""

import base64

DATA_URL_PREFIX = "data:image/png;base64,"

# PNG 인코딩 이후 이미지 하나의 최대 바이트 수. 초과하면 첨부를 거부해
# 요청 payload가 과도하게 커지는 것을 막는다. chat_panel.py가 붙여넣기
# 단계에서 긴 변 1600px로 미리 리사이즈하므로, 실제 스크린샷은 리사이즈
# 이후 이 값을 넘는 경우가 거의 없다(사유는 완료 보고서 참고).
MAX_ENCODED_IMAGE_BYTES = 5 * 1024 * 1024

# 한 번에 pending 상태로 들고 있을 수 있는 이미지 개수 제한(4단계
# "합리적인 개수 제한" - 구조가 복잡해지지 않는 선에서 정한 값).
MAX_PENDING_IMAGES = 4


class ImageAttachmentError(Exception):
    """이미지 첨부를 계속 진행할 수 없을 때(크기 초과 등) 발생한다.

    KeyboardInterrupt/SystemExit는 Exception이 아니므로 이 클래스와
    무관하게 항상 그대로 전파된다.
    """


def encode_png_bytes_to_data_url(png_bytes: bytes) -> str:
    """PNG로 인코딩된 bytes를 base64 data URL 문자열로 바꾼다."""
    return DATA_URL_PREFIX + base64.b64encode(png_bytes).decode("ascii")


def validate_encoded_image_size(png_bytes: bytes) -> None:
    """PNG bytes가 허용 크기(MAX_ENCODED_IMAGE_BYTES)를 넘으면 예외를 던진다."""
    if len(png_bytes) > MAX_ENCODED_IMAGE_BYTES:
        size_mb = len(png_bytes) / (1024 * 1024)
        raise ImageAttachmentError(
            f"이미지가 너무 커서 첨부할 수 없습니다({size_mb:.1f}MB). "
            "더 작은 영역을 캡처해 다시 시도해주세요."
        )


def build_input_text_item(text: str) -> dict:
    """OpenAI Responses API의 input_text content item을 만든다."""
    return {"type": "input_text", "text": text}


def build_input_image_item(data_url: str) -> dict:
    """OpenAI Responses API의 input_image content item을 만든다."""
    return {"type": "input_image", "image_url": data_url, "detail": "auto"}


def build_user_message_content(text: str, data_urls: list[str]) -> str | list[dict]:
    """사용자 메시지의 content를 만든다.

    이미지가 없으면 기존과 완전히 동일하게 순수 문자열을 그대로
    반환한다 - 텍스트 전용 대화가 예전과 동일한 모양으로 동작해야 한다.
    이미지가 있으면 OpenAI가 받아들이는 content item 리스트를 만든다.
    text가 비어 있지 않을 때만 input_text 항목을 넣는다 - 이미지만
    보내는 경우(텍스트 없이 전송)에도 빈 텍스트 항목을 억지로 넣지
    않는다.
    """
    if not data_urls:
        return text

    content: list[dict] = []
    stripped = text.strip()
    if stripped:
        content.append(build_input_text_item(stripped))
    for data_url in data_urls:
        content.append(build_input_image_item(data_url))
    return content


def extract_data_urls_from_content(content) -> list[str]:
    """content(str 또는 content item 리스트)에서 이미지 data URL만 뽑아낸다.

    content가 문자열이면(텍스트 전용 메시지) 이미지가 없으므로 빈
    리스트를 반환한다 - 문자열의 문자를 순회하는 실수를 막는다.
    """
    if isinstance(content, str):
        return []
    return [item["image_url"] for item in content if isinstance(item, dict) and item.get("type") == "input_image"]


def extract_text_from_content(content) -> str:
    """content에서 텍스트 부분만 뽑아 이어붙인다. 텍스트가 없으면 빈 문자열."""
    if isinstance(content, str):
        return content
    texts = [item["text"] for item in content if isinstance(item, dict) and item.get("type") == "input_text"]
    return "\n".join(texts)
