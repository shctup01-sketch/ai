"""'+' 버튼으로 선택한 일반 파일(이미지 제외)을 Chief Brain이 읽을 수 있는
텍스트로 바꾸는 순수 로직.

PySide6에 전혀 의존하지 않는다 - 파일 선택 대화상자(QFileDialog)를 띄우고
디스크에서 실제로 파일을 읽는 것은 chat_panel.py의 몫이고, 이 파일은
"이미 읽은 파일명/MIME 타입/크기/(텍스트 파일이면) 내용"만 받아 사람이
읽을 수 있는 첨부 텍스트 블록으로 바꾸는 것과, 파일 종류 판별/민감 파일
차단 같은 순수 판단만 담당한다. 그래야 PySide6.QtGui를 import할 수 없는
환경에서도 이 파일의 로직을 실제로 실행해 테스트할 수 있다.

27단계 조사 결과(추측 금지 원칙에 따른 SDK 실제 확인): 설치된 openai
SDK(3.2.0)의 ResponseInputFileParam(response_input_file_param.py)에는
input_file 타입과 file_data 필드가 존재한다. 하지만 Responses API 쪽
file_data의 문서 문자열은 "The content of the file to be sent to the
model."이라고만 되어 있을 뿐, base64 data URL 형식인지 순수 base64
문자열인지를 SDK 타입 정의만으로는 확정할 수 없었다(인접한 Chat
Completions API의 FileFile.file_data는 "base64 encoded file data"라고
명시하지만, Responses API가 동일한 문자열 규격을 쓴다는 보장은 SDK
코드만으로는 얻을 수 없었고, 패키지에 번들된 api.md에도 file_data 사용
예시가 없었다). "추측 금지" 지침에 따라 이번 단계에서는 input_file
content item을 실제로 만들어 전송하지 않는다 - PDF/docx/xlsx 등
텍스트가 아닌 문서 파일은 v1에서 파일명/MIME 타입/크기 정보만 사람이
읽을 수 있는 텍스트로 Chief Brain에 전달한다(조용히 무시하지 않고,
"이 파일 형식은 아직 내용을 직접 전달하지 않는다"는 사실을 명시한다).
"""

import os

# "+" 버튼으로 선택한 파일이 이 확장자면 image_content.py가 다루는
# input_image 경로로 그대로 재사용한다(별도 처리 없음, chat_panel.py가
# QImage로 읽어 기존 Ctrl+V 이미지와 완전히 동일한 파이프라인을 탄다).
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}

# UTF-8 텍스트로 읽어 Chief Brain 입력에 실제 내용을 그대로 포함할 수
# 있는 확장자.
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".json", ".csv", ".log",
    ".yaml", ".yml", ".toml", ".ini",
    ".html", ".htm", ".css", ".js", ".ts", ".tsx", ".jsx",
}

# 텍스트 파일 하나를 읽어 들이는 최대 크기(바이트). 9단계 사양이 권장한
# 범위(1~2MB) 중 상단값을 택했다 - 텍스트는 그대로 토큰이 되어 이미지
# (base64, 5MB)보다 정보 밀도가 높으므로 더 낮게 잡는다.
MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024

# 한 번에 첨부할 수 있는 항목(이미지 + 일반 파일 합계) 총 개수. 이미지
# 자체의 개수 제한(image_content.MAX_PENDING_IMAGES=4)과는 별개로,
# 전체 첨부 총량을 한 번 더 제한한다(9단계 "이미지 포함 총 5~10개").
MAX_TOTAL_ATTACHMENTS = 8

# 10단계 보안 요구사항 - 사용자가 명시적으로 선택했더라도 이 이름/확장자
# 패턴에 해당하면 첨부를 차단한다(자동 탐색이 아니라 "선택한 파일에 대한
# 안전장치"라는 점에 유의).
_SENSITIVE_NAME_KEYWORDS = ("credential", "secret", "private_key", "private-key", "privatekey")
_SENSITIVE_EXTENSIONS = {".pem", ".key"}


class AttachmentError(Exception):
    """파일 첨부를 계속 진행할 수 없을 때(민감 파일/크기 초과 등) 발생한다."""


def _basename_lower(path_or_name: str) -> str:
    return os.path.basename(path_or_name).lower()


def is_sensitive_filename(path_or_name: str) -> bool:
    """.env/.env.*/credential/secret/private key/*.pem/*.key 패턴을 막는다."""
    name = _basename_lower(path_or_name)
    if name == ".env" or name.startswith(".env."):
        return True
    _, ext = os.path.splitext(name)
    if ext in _SENSITIVE_EXTENSIONS:
        return True
    return any(keyword in name for keyword in _SENSITIVE_NAME_KEYWORDS)


def guess_attachment_kind(path_or_name: str) -> str:
    """확장자를 보고 "image"/"text"/"binary" 중 하나로 분류한다.

    알려지지 않은 확장자는 전부 "binary"로 취급한다 - PDF/docx/xlsx를
    포함해, 내용을 직접 읽지 않고 파일 정보만 전달하는 경로로 안전하게
    떨어진다.
    """
    _, ext = os.path.splitext(_basename_lower(path_or_name))
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in TEXT_EXTENSIONS:
        return "text"
    return "binary"


def format_file_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"


def build_attachment_text_block(name: str, mime_type: str, size: int, text_content: str | None) -> str:
    """첨부 파일 하나를 Chief Brain이 읽을 텍스트 블록으로 만든다.

    text_content가 있으면(텍스트 파일) 실제 내용을 그대로 포함하고,
    없으면(바이너리/문서 파일) 파일명/MIME 타입/크기 정보와 함께 "이
    파일 형식은 내용을 직접 전달하지 않는다"는 사실을 명시한다 - 조용히
    무시하지 않는다.
    """
    size_display = format_file_size(size)
    if text_content is not None:
        return f"[첨부 파일: {name}]\n\n내용:\n{text_content}"
    return (
        f"[첨부 파일: {name}] ({mime_type}, {size_display}) - "
        "이 파일 형식은 현재 내용을 직접 전달하지 않고 파일 이름/종류/크기 정보만 전달됩니다."
    )


def build_combined_text(user_text: str, attachment_blocks: list[str]) -> str:
    """사용자가 입력한 텍스트 뒤에 첨부 파일 블록들을 이어붙인다.

    사용자 텍스트가 비어 있으면 생략한다(첨부 블록만 남는 "파일만 전송"
    케이스를 지원한다). 반환값은 image_content.build_user_message_content()의
    text 인자에 그대로 넘기면 된다 - 이미지가 없으면 이 문자열 그대로가
    content가 되고, 있으면 input_text 항목의 text가 된다.
    """
    parts: list[str] = []
    stripped = user_text.strip()
    if stripped:
        parts.append(stripped)
    parts.extend(attachment_blocks)
    return "\n\n".join(parts)
