from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QTimer, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai import image_content
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

        # 이미지 붙여넣기 실패/개수 제한/크기 초과 등을 짧게 알려주는 상태
        # 표시줄. 평소에는 숨겨져 있다.
        self.paste_status_label = QLabel("")
        self.paste_status_label.setObjectName("PasteStatusLabel")
        self.paste_status_label.setStyleSheet("color: #e06c75;")
        self.paste_status_label.setVisible(False)
        layout.addWidget(self.paste_status_label)

        input_row = QHBoxLayout()
        self.chat_input = ChatInput()
        self.chat_input.send_requested.connect(self._on_send_clicked)
        self.chat_input.image_pasted.connect(self._on_image_pasted)
        self.chat_input.image_paste_failed.connect(self._on_paste_error)
        self.send_button = QPushButton("보내기")
        self.send_button.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self.chat_input)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        self._history: list[dict] = []
        self._waiting_for_response = False
        # 보내기 전까지만 들고 있는 붙여넣은 이미지들. 각 항목은
        # {"data_url": str, "thumbnail": QPixmap} 형태다 - data_url은
        # 그대로 전송 대상(OpenAI 요청)에 쓰이고, thumbnail은 화면
        # 표시(미리보기/말풍선)에만 쓰인다.
        self._pending_images: list[dict] = []

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
        if len(self._pending_images) >= image_content.MAX_PENDING_IMAGES:
            self._show_paste_status(
                f"이미지는 한 번에 최대 {image_content.MAX_PENDING_IMAGES}장까지 첨부할 수 있습니다."
            )
            return

        try:
            png_bytes = _encode_image_to_png_bytes(image)
            image_content.validate_encoded_image_size(png_bytes)
        except image_content.ImageAttachmentError as exc:
            self._show_paste_status(str(exc))
            return
        except Exception:
            # 알 수 없는 인코딩 실패도 앱 전체를 죽이지 않고 안전하게
            # 알린다. KeyboardInterrupt/SystemExit는 Exception이 아니므로
            # 여기서 잡히지 않고 그대로 전파된다.
            self._show_paste_status("이미지를 처리하는 중 오류가 발생했습니다.")
            return

        data_url = image_content.encode_png_bytes_to_data_url(png_bytes)
        thumbnail = _make_thumbnail_pixmap(image)
        self._pending_images.append({"data_url": data_url, "thumbnail": thumbnail})
        self._refresh_image_preview()
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

    def _on_send_clicked(self):
        if self._waiting_for_response:
            return
        text = self.chat_input.toPlainText().strip()
        data_urls = [pending["data_url"] for pending in self._pending_images]
        if not text and not data_urls:
            return

        display_text = text if text else f"[이미지 {len(data_urls)}장 첨부]"
        thumbnails = [pending["thumbnail"] for pending in self._pending_images] or None
        self._add_message(display_text, is_user=True, thumbnails=thumbnails)
        self.chat_input.clear()

        content = image_content.build_user_message_content(text, data_urls)
        self._history.append({"role": "user", "content": content})

        self._pending_images = []
        self._refresh_image_preview()
        self._clear_paste_status()

        self._set_waiting(True)
        self.chief_brain_service.plan_work(list(self._history))

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
