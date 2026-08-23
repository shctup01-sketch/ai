import mimetypes
import os

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai import file_content, image_content, screen_capture
from ai.brain_response import BrainResponse
from ai.chief_brain_compat import ChiefBrainCompatError, adapt_chief_brain_plan_to_brain_response
from ai.chief_brain_plan import ChiefBrainPlan
from ai.chief_brain_service import ChiefBrainService

BRAIN_GREETING = (
    "안녕하세요. AI Development Studio의 Brain입니다.\n"
    "만들고 싶은 프로그램이나 게임을 말씀해주세요."
)

# Win+Shift+S로 캡처한 화면은 매우 클 수 있다. 오류 화면의 글자를 읽을 수
# 있어야 하므로 과도하게 줄이지 않되, 요청 크기/메모리 사용을 억제하기
# 위해 긴 변을 이 값(px)으로 제한한다(비율은 유지, 이보다 작으면 그대로
# 둔다). 근거는 완료 보고서에 명시한다.
MAX_IMAGE_DIMENSION_PX = 1600

# 미리보기 스트립/채팅 말풍선에 보여줄 썸네일 한 변의 크기(px).
THUMBNAIL_SIZE_PX = 64


class ChatInput(QTextEdit):
    send_requested = Signal()
    # 클립보드에 이미지가 있어 Ctrl+V를 이미지 붙여넣기로 처리했을 때 발생.
    image_pasted = Signal(QImage)
    # 클립보드에 이미지가 있다고 표시되었지만 실제로 읽어올 수 없었을 때 발생.
    image_paste_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("메시지를 입력하세요... (Enter: 줄바꿈, Ctrl+Enter: 보내기)")
        self.setFixedHeight(90)

    def keyPressEvent(self, event):
        is_enter_key = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if is_enter_key and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.send_requested.emit()
            return
        super().keyPressEvent(event)

    def insertFromMimeData(self, source):
        # QTextEdit이 붙여넣기(Ctrl+V 포함)마다 호출하는 지점을 그대로
        # 재정의한다 - 클립보드에 이미지가 있으면 이미지 첨부로 처리하고,
        # 그렇지 않으면(텍스트 등) 기존 동작(super() 호출)을 그대로
        # 유지한다. 텍스트 붙여넣기 동작은 한 줄도 바꾸지 않는다.
        if source.hasImage():
            clipboard_image = QApplication.clipboard().image()
            if clipboard_image.isNull():
                self.image_paste_failed.emit("클립보드 이미지를 읽을 수 없습니다.")
            else:
                self.image_pasted.emit(clipboard_image)
            return
        super().insertFromMimeData(source)


def _build_attachment_display_text(text: str, image_count: int, file_count: int) -> str:
    """전송 시 사용자 말풍선에 보여줄 텍스트를 만든다.

    텍스트가 있으면 그대로 쓴다. 텍스트가 없으면(이미지/파일만 전송)
    무엇이 몇 개 첨부됐는지 요약한다 - 26단계의 "[이미지 N장 첨부]"
    표기를 그대로 포함하면서(이미지만 있는 경우 문구가 완전히 동일),
    파일이 있으면 이어붙인다.
    """
    if text:
        return text
    parts = []
    if image_count:
        parts.append(f"이미지 {image_count}장")
    if file_count:
        parts.append(f"파일 {file_count}개")
    return f"[{' + '.join(parts)} 첨부]" if parts else ""


def _build_message_row(text: str, is_user: bool, thumbnails: list[QPixmap] | None = None) -> QWidget:
    row = QWidget()
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 4, 0, 4)

    if thumbnails:
        # 이미지가 첨부된 메시지만 이 경로를 탄다 - 순수 텍스트 메시지는
        # 아래 else 분기(기존 코드 그대로)를 그대로 사용해 기존 화면
        # 모양을 전혀 바꾸지 않는다.
        bubble = QWidget()
        bubble.setObjectName("UserBubble" if is_user else "BrainBubble")
        # 일반 QWidget은 스타일시트의 background-color를 기본적으로
        # 그리지 않는다(QLabel과 다른 점) - 이 속성을 켜야 말풍선 배경색이
        # 실제로 보인다.
        bubble.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bubble.setMaximumWidth(420)
        bubble_layout = QVBoxLayout(bubble)
        bubble_layout.setContentsMargins(8, 8, 8, 8)

        thumb_row = QHBoxLayout()
        for pixmap in thumbnails:
            thumb_label = QLabel()
            thumb_label.setPixmap(pixmap)
            thumb_label.setFixedSize(THUMBNAIL_SIZE_PX, THUMBNAIL_SIZE_PX)
            thumb_row.addWidget(thumb_label)
        thumb_row.addStretch(1)
        bubble_layout.addLayout(thumb_row)

        if text:
            text_label = QLabel(text)
            text_label.setWordWrap(True)
            text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            bubble_layout.addWidget(text_label)
    else:
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bubble.setMaximumWidth(420)
        bubble.setObjectName("UserBubble" if is_user else "BrainBubble")

    if is_user:
        row_layout.addStretch(1)
        row_layout.addWidget(bubble)
    else:
        row_layout.addWidget(bubble)
        row_layout.addStretch(1)

    return row


def _resize_image_if_needed(image: QImage) -> QImage:
    longest_side = max(image.width(), image.height())
    if longest_side <= MAX_IMAGE_DIMENSION_PX:
        return image
    return image.scaled(
        MAX_IMAGE_DIMENSION_PX,
        MAX_IMAGE_DIMENSION_PX,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def _encode_image_to_png_bytes(image: QImage) -> bytes:
    resized = _resize_image_if_needed(image)
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    saved = resized.save(buffer, "PNG")
    buffer.close()
    if not saved:
        raise image_content.ImageAttachmentError("이미지를 PNG로 변환하지 못했습니다.")
    return bytes(byte_array)


def _make_thumbnail_pixmap(image: QImage) -> QPixmap:
    pixmap = QPixmap.fromImage(image)
    return pixmap.scaled(
        THUMBNAIL_SIZE_PX,
        THUMBNAIL_SIZE_PX,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class ChatPanel(QWidget):
    # 기존 signal - 단일 development/research 요청(BrainResponse, chief_brain_compat.py로
    # 변환된 것)이 준비되면 발생한다. MainWindow의 기존 처리(_on_plan_ready)를
    # 그대로 재사용하기 위해 이름/타입을 바꾸지 않는다.
    plan_ready = Signal(object)
    # 신규 signal - 여러 단계로 이루어졌거나(2개 이상) 기존 BrainResponse로
    # 표현할 수 없는 단일 task_type(예: kmong_publish)의 ChiefBrainPlan이
    # 준비되면 발생한다.
    chief_plan_ready = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title_label = QLabel("Brain")
        title_label.setObjectName("CenterPrompt")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        subtitle_label = QLabel("원하는 것을 말씀해주세요. 제가 계획하고 필요한 AI와 함께 작업하겠습니다.")
        subtitle_label.setObjectName("CenterSubtitle")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("ChatScrollArea")
        self.scroll_area.setWidgetResizable(True)

        self.messages_container = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.addStretch(1)
        self.scroll_area.setWidget(self.messages_container)
        layout.addWidget(self.scroll_area, stretch=1)

        # 붙여넣은 이미지의 미리보기 스트립. 이미지가 하나도 없으면 숨긴다.
        self.image_preview_strip = QWidget()
        self.image_preview_strip.setObjectName("ImagePreviewStrip")
        self.image_preview_layout = QHBoxLayout(self.image_preview_strip)
        self.image_preview_layout.setContentsMargins(0, 0, 0, 4)
        self.image_preview_layout.addStretch(1)
        self.image_preview_strip.setVisible(False)
        layout.addWidget(self.image_preview_strip)

        # "+" 버튼으로 첨부한 일반 파일(이미지 제외)의 미리보기 스트립.
        # 27단계 - 이미지와 별도 목록/위젯으로 둔다(5단계 "가장 안전한
        # 최소 변경" 선택 - 이미 검증된 이미지 미리보기 코드를 전혀
        # 건드리지 않는다).
        self.file_preview_strip = QWidget()
        self.file_preview_strip.setObjectName("FilePreviewStrip")
        self.file_preview_layout = QHBoxLayout(self.file_preview_strip)
        self.file_preview_layout.setContentsMargins(0, 0, 0, 4)
        self.file_preview_layout.addStretch(1)
        self.file_preview_strip.setVisible(False)
        layout.addWidget(self.file_preview_strip)

        # 이미지 붙여넣기/파일 첨부 실패/개수 제한/크기 초과 등을 짧게
        # 알려주는 상태 표시줄. 평소에는 숨겨져 있다.
        self.paste_status_label = QLabel("")
        self.paste_status_label.setObjectName("PasteStatusLabel")
        self.paste_status_label.setStyleSheet("color: #e06c75;")
        self.paste_status_label.setVisible(False)
        layout.addWidget(self.paste_status_label)

        input_row = QHBoxLayout()
        self.attach_button = QPushButton("+")
        self.attach_button.setObjectName("AttachButton")
        self.attach_button.setFixedWidth(32)
        self.attach_button.setToolTip("파일 첨부")
        self.attach_button.clicked.connect(self._on_attach_button_clicked)
        # 28단계 - "+" 버튼을 메뉴로 바꾸지 않고 별도의 작은 버튼을 둔다
        # (7단계가 명시적으로 허용한 대안). "+" 버튼을 QMenu로 바꾸면
        # 27단계에서 이미 검증된 "+ 클릭 -> 바로 QFileDialog" 흐름과 그
        # 흐름을 검증하는 기존 회귀 테스트들을 건드릴 위험이 커서, 회귀
        # 위험이 가장 작은 방식을 선택했다(이유는 완료 보고서 참고).
        self.screen_capture_button = QPushButton("화면")
        self.screen_capture_button.setObjectName("ScreenCaptureButton")
        self.screen_capture_button.setFixedWidth(40)
        self.screen_capture_button.setToolTip("현재 화면 첨부")
        self.screen_capture_button.clicked.connect(self._on_screen_capture_button_clicked)
        self.chat_input = ChatInput()
        self.chat_input.send_requested.connect(self._on_send_clicked)
        self.chat_input.image_pasted.connect(self._on_image_pasted)
        self.chat_input.image_paste_failed.connect(self._on_paste_error)
        self.send_button = QPushButton("보내기")
        self.send_button.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self.attach_button)
        input_row.addWidget(self.screen_capture_button)
        input_row.addWidget(self.chat_input)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        self._history: list[dict] = []
        self._waiting_for_response = False
        # 59단계 - MainWindow가 "지금 project checkpoint가 떠 있는지"를
        # 안다(PersistentProjectState/checkpoint 상태는 여기서 전혀
        # 모른다 - ChatPanel은 계속 project를 모르는 채로 둔다, §0 "전체
        # 채팅 시스템 재작성 금지"). MainWindow가 이 콜백을 등록해두면,
        # 메시지를 보낼 때마다 먼저 이 콜백에게 "네가 처리할래?"라고
        # 물어본다 - True를 돌려주면(체크포인트 중이라 Brain 상담으로
        # 가로챈 경우) 기존 plan_work() 호출을 건너뛴다. None이거나
        # False를 돌려주면(체크포인트가 없거나 콜백 자체가 없는 경우)
        # 기존 흐름을 그대로 탄다 - project가 없는 기존 채팅은 전혀
        # 영향받지 않는다(§7).
        self._checkpoint_consultation_handler = None
        # 보내기 전까지만 들고 있는 첨부 이미지들(Ctrl+V로 붙여넣은 것과
        # "+" 버튼으로 선택한 이미지 파일 모두 이 목록 하나를 공유한다 -
        # 2단계 "동일한 첨부 구조" 요구사항). 각 항목은
        # {"data_url": str, "thumbnail": QPixmap} 형태다 - data_url은
        # 그대로 전송 대상(OpenAI 요청)에 쓰이고, thumbnail은 화면
        # 표시(미리보기/말풍선)에만 쓰인다.
        self._pending_images: list[dict] = []
        # 보내기 전까지만 들고 있는 첨부 일반 파일(이미지 제외)들. 각
        # 항목은 {"kind": "text_file" | "binary_file", "name": str,
        # "mime_type": str, "size": int, "text_content": str | None}
        # 형태다 - text_content는 텍스트 파일일 때만 채워진다.
        self._pending_files: list[dict] = []

        # 사용자 입력의 1차 판단자는 Chief Brain이다(23단계) - 기존
        # BrainService/OpenAIProvider는 삭제하지 않고 남겨두지만, 이 화면은
        # 더 이상 그것을 직접 호출하지 않는다. 단일 development/research
        # 요청은 chief_brain_compat.py를 거쳐 기존 UI 흐름 그대로 재사용한다.
        self.chief_brain_service = ChiefBrainService(parent=self)
        self.chief_brain_service.plan_ready.connect(self._on_chief_brain_plan_ready)
        self.chief_brain_service.error_occurred.connect(self._on_brain_error)

        self._add_message(BRAIN_GREETING, is_user=False)

    def _add_message(self, text: str, is_user: bool, thumbnails: list[QPixmap] | None = None):
        row = _build_message_row(text, is_user, thumbnails)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, row)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_image_pasted(self, image: QImage):
        self._attach_image(image)

    def _attach_image(self, image: QImage) -> bool:
        """QImage 하나를 검증/인코딩해 self._pending_images에 추가한다.

        Ctrl+V 붙여넣기(_on_image_pasted)와 "+" 버튼으로 선택한 이미지
        파일(_add_file_attachment) 양쪽이 이 메서드 하나를 공유한다 -
        2단계 "동일한 첨부 구조 사용, 중복 구현 최소화" 요구사항.
        """
        if len(self._pending_images) >= image_content.MAX_PENDING_IMAGES:
            self._show_paste_status(
                f"이미지는 한 번에 최대 {image_content.MAX_PENDING_IMAGES}장까지 첨부할 수 있습니다."
            )
            return False
        if self._total_attachment_count() >= file_content.MAX_TOTAL_ATTACHMENTS:
            self._show_paste_status(
                f"첨부는 한 번에 최대 {file_content.MAX_TOTAL_ATTACHMENTS}개까지 가능합니다."
            )
            return False

        try:
            png_bytes = _encode_image_to_png_bytes(image)
            image_content.validate_encoded_image_size(png_bytes)
        except image_content.ImageAttachmentError as exc:
            self._show_paste_status(str(exc))
            return False
        except Exception:
            # 알 수 없는 인코딩 실패도 앱 전체를 죽이지 않고 안전하게
            # 알린다. KeyboardInterrupt/SystemExit는 Exception이 아니므로
            # 여기서 잡히지 않고 그대로 전파된다.
            self._show_paste_status("이미지를 처리하는 중 오류가 발생했습니다.")
            return False

        data_url = image_content.encode_png_bytes_to_data_url(png_bytes)
        thumbnail = _make_thumbnail_pixmap(image)
        self._pending_images.append({"data_url": data_url, "thumbnail": thumbnail})
        self._refresh_image_preview()
        self._clear_paste_status()
        return True

    def _total_attachment_count(self) -> int:
        return len(self._pending_images) + len(self._pending_files)

    def _on_attach_button_clicked(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "파일 첨부", "", "모든 파일 (*)")
        for path in paths:
            self._add_file_attachment(path)

    def _on_screen_capture_button_clicked(self):
        # 사용자가 이 버튼을 직접 눌렀을 때만 호출된다 - 자동/주기적
        # 캡처는 없다. 캡처된 이미지는 곧바로 전송되지 않고 Ctrl+V/"+"
        # 이미지와 완전히 동일하게 _attach_image()를 거쳐 pending 상태로만
        # 추가된다(6단계 "캡처 즉시 자동 전송하지 않는다").
        try:
            image = screen_capture.capture_primary_screen()
        except screen_capture.ScreenCaptureError as exc:
            self._show_paste_status(str(exc))
            return
        except Exception:
            # 알 수 없는 캡처 실패도 앱 전체를 죽이지 않고 안전하게
            # 알린다. KeyboardInterrupt/SystemExit는 Exception이 아니므로
            # 여기서 잡히지 않고 그대로 전파된다.
            self._show_paste_status("현재 화면을 캡처하지 못했습니다.")
            return

        self._attach_image(image)

    def _add_file_attachment(self, path: str):
        name = os.path.basename(path)

        if file_content.is_sensitive_filename(path):
            self._show_paste_status(f"'{name}' 파일은 민감한 정보를 담고 있을 수 있어 첨부할 수 없습니다.")
            return

        kind = file_content.guess_attachment_kind(path)

        if kind == "image":
            # "+"로 선택한 이미지 파일도 Ctrl+V와 완전히 동일한
            # _pending_images/_attach_image 경로를 그대로 탄다.
            image = QImage(path)
            if image.isNull():
                self._show_paste_status(f"'{name}' 이미지를 읽을 수 없습니다.")
                return
            self._attach_image(image)
            return

        if self._total_attachment_count() >= file_content.MAX_TOTAL_ATTACHMENTS:
            self._show_paste_status(
                f"첨부는 한 번에 최대 {file_content.MAX_TOTAL_ATTACHMENTS}개까지 가능합니다."
            )
            return

        try:
            size = os.path.getsize(path)
        except OSError:
            self._show_paste_status(f"'{name}' 파일 정보를 읽을 수 없습니다.")
            return

        mime_type, _ = mimetypes.guess_type(name)
        mime_type = mime_type or "application/octet-stream"

        if kind == "text":
            if size > file_content.MAX_TEXT_FILE_BYTES:
                self._show_paste_status(
                    f"'{name}' 파일이 너무 커서 첨부할 수 없습니다"
                    f"({file_content.format_file_size(size)}, 최대 "
                    f"{file_content.format_file_size(file_content.MAX_TEXT_FILE_BYTES)})."
                )
                return
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    text_content = fh.read()
            except (OSError, UnicodeDecodeError):
                self._show_paste_status(f"'{name}' 파일을 텍스트로 읽을 수 없습니다.")
                return
            self._pending_files.append(
                {"kind": "text_file", "name": name, "mime_type": mime_type, "size": size, "text_content": text_content}
            )
        else:
            self._pending_files.append(
                {"kind": "binary_file", "name": name, "mime_type": mime_type, "size": size, "text_content": None}
            )

        self._refresh_file_preview()
        self._clear_paste_status()

    def _on_paste_error(self, message: str):
        self._show_paste_status(message)

    def _show_paste_status(self, message: str):
        self.paste_status_label.setText(message)
        self.paste_status_label.setVisible(True)

    def _clear_paste_status(self):
        self.paste_status_label.clear()
        self.paste_status_label.setVisible(False)

    def _refresh_image_preview(self):
        # addStretch(1)로 넣어둔 마지막 항목만 남기고 썸네일 위젯을 전부
        # 지운 뒤 현재 pending 목록을 기준으로 다시 그린다.
        while self.image_preview_layout.count() > 1:
            item = self.image_preview_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for index, pending in enumerate(self._pending_images):
            item_widget = self._build_pending_image_widget(index, pending["thumbnail"])
            self.image_preview_layout.insertWidget(self.image_preview_layout.count() - 1, item_widget)

        self.image_preview_strip.setVisible(bool(self._pending_images))

    def _build_pending_image_widget(self, index: int, thumbnail: QPixmap) -> QWidget:
        item = QWidget()
        item.setObjectName("PendingImageItem")
        item.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        item_layout = QVBoxLayout(item)
        item_layout.setContentsMargins(2, 2, 2, 2)

        thumb_label = QLabel()
        thumb_label.setPixmap(thumbnail)
        thumb_label.setFixedSize(THUMBNAIL_SIZE_PX, THUMBNAIL_SIZE_PX)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        item_layout.addWidget(thumb_label)

        remove_button = QPushButton("삭제")
        remove_button.setFixedHeight(20)
        remove_button.clicked.connect(lambda _checked=False, i=index: self._remove_pending_image(i))
        item_layout.addWidget(remove_button)

        return item

    def _remove_pending_image(self, index: int):
        if 0 <= index < len(self._pending_images):
            del self._pending_images[index]
            self._refresh_image_preview()

    def _refresh_file_preview(self):
        while self.file_preview_layout.count() > 1:
            item = self.file_preview_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for index, pending in enumerate(self._pending_files):
            item_widget = self._build_pending_file_widget(index, pending)
            self.file_preview_layout.insertWidget(self.file_preview_layout.count() - 1, item_widget)

        self.file_preview_strip.setVisible(bool(self._pending_files))

    def _build_pending_file_widget(self, index: int, pending: dict) -> QWidget:
        item = QWidget()
        item.setObjectName("PendingFileItem")
        item.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        item_layout = QVBoxLayout(item)
        item_layout.setContentsMargins(6, 4, 6, 4)

        info_label = QLabel(f"[파일] {pending['name']}\n{file_content.format_file_size(pending['size'])}")
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setMaximumWidth(110)
        item_layout.addWidget(info_label)

        remove_button = QPushButton("삭제")
        remove_button.setFixedHeight(20)
        remove_button.clicked.connect(lambda _checked=False, i=index: self._remove_pending_file(i))
        item_layout.addWidget(remove_button)

        return item

    def _remove_pending_file(self, index: int):
        if 0 <= index < len(self._pending_files):
            del self._pending_files[index]
            self._refresh_file_preview()

    def _on_send_clicked(self):
        if self._waiting_for_response:
            return
        text = self.chat_input.toPlainText().strip()
        data_urls = [pending["data_url"] for pending in self._pending_images]
        file_blocks = [
            file_content.build_attachment_text_block(
                pending["name"], pending["mime_type"], pending["size"], pending["text_content"]
            )
            for pending in self._pending_files
        ]
        if not text and not data_urls and not file_blocks:
            return

        display_text = _build_attachment_display_text(text, len(data_urls), len(self._pending_files))
        thumbnails = [pending["thumbnail"] for pending in self._pending_images] or None
        self._add_message(display_text, is_user=True, thumbnails=thumbnails)
        self.chat_input.clear()

        self._pending_images = []
        self._pending_files = []
        self._refresh_image_preview()
        self._refresh_file_preview()
        self._clear_paste_status()

        self._set_waiting(True)

        # 59단계 - project checkpoint가 떠 있으면 MainWindow가 미리 등록해
        # 둔 콜백에게 먼저 맡긴다(handler(text) -> bool). True를 돌려주면
        # (Brain 상담으로 이미 처리를 시작한 경우) 여기서 끝난다 - 이
        # 질문/답변은 plan_work()용 _history에 넣지 않는다(§11 - 상담
        # 질답을 계획 생성 대화 기록에 섞어서 다음 plan_work 호출마다
        # 반복 전송하지 않는다). handler가 없거나 False를 돌려주면(체크
        # 포인트가 없는 평소 상태, §7) 기존 흐름을 그대로 탄다 - project가
        # 없는 기존 채팅은 전혀 영향받지 않는다.
        if self._checkpoint_consultation_handler is not None and self._checkpoint_consultation_handler(text):
            return

        combined_text = file_content.build_combined_text(text, file_blocks)
        content = image_content.build_user_message_content(combined_text, data_urls)
        self._history.append({"role": "user", "content": content})
        self.chief_brain_service.plan_work(list(self._history))

    def set_checkpoint_consultation_handler(self, handler):
        """59단계 - MainWindow가 "지금 project checkpoint가 떠 있는지"를
        판단해 대신 처리할 콜백을 등록한다. handler(text: str) -> bool.
        ChatPanel은 project/checkpoint 개념을 전혀 모른 채로 남는다 -
        이 콜백 하나만 갖고 있을 뿐이다.
        """
        self._checkpoint_consultation_handler = handler

    def add_assistant_note(self, text: str):
        """59단계 - Brain 상담 답변 등을 화면에만 보여준다(_history에는
        넣지 않는다 - §11, 다음 plan_work 호출이 이 내용을 다시 반복해서
        보내지 않도록 한다)."""
        self._add_message(text, is_user=False)

    def set_waiting(self, waiting: bool):
        """59단계 - MainWindow가 비동기 Brain 상담 응답을 받은 뒤 입력을
        다시 활성화할 때 쓰는 공개 메서드다(기존 _set_waiting 그대로 재사용)."""
        self._set_waiting(waiting)

    def focus_input(self):
        """59단계(사용자 검토) §4 - "수정 요청" 버튼 등에서 메인 채팅
        입력창으로 사용자의 시선/커서를 옮길 때 쓴다."""
        self.chat_input.setFocus()

    def _on_chief_brain_plan_ready(self, plan: ChiefBrainPlan):
        self._history.append({"role": "assistant", "content": plan.user_reply})
        self._add_message(plan.user_reply, is_user=False)
        self._set_waiting(False)

        # 단일 development/research(그리고 추가 질문/일반 대화)는 기존
        # BrainResponse 호환 어댑터로 변환해 기존 UI 흐름을 그대로 쓴다.
        # 2개 이상의 step이거나 development/research가 아닌 단일 step
        # (예: kmong_publish)이면 어댑터가 명시적으로 거부하므로, 그때만
        # 새 chief_plan_ready 신호로 넘긴다 - 일부만 조용히 반영하지 않는다.
        try:
            brain_response = adapt_chief_brain_plan_to_brain_response(plan)
        except ChiefBrainCompatError:
            self.chief_plan_ready.emit(plan)
            return

        if brain_response.plan_ready:
            self.plan_ready.emit(brain_response)

    def _on_brain_error(self, message: str):
        self._add_message(f"Brain 응답 중 오류가 발생했습니다: {message}", is_user=False)
        self._set_waiting(False)

    def _set_waiting(self, waiting: bool):
        self._waiting_for_response = waiting
        self.send_button.setEnabled(not waiting)
