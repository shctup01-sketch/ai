from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai.brain_service import BrainService

BRAIN_GREETING = (
    "안녕하세요. AI Development Studio의 Brain입니다.\n"
    "만들고 싶은 프로그램이나 게임을 말씀해주세요."
)


class ChatInput(QTextEdit):
    send_requested = Signal()

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


def _build_message_row(text: str, is_user: bool) -> QWidget:
    row = QWidget()
    row_layout = QHBoxLayout(row)
    row_layout.setContentsMargins(0, 4, 0, 4)

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


class ChatPanel(QWidget):
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

        input_row = QHBoxLayout()
        self.chat_input = ChatInput()
        self.chat_input.send_requested.connect(self._on_send_clicked)
        self.send_button = QPushButton("보내기")
        self.send_button.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self.chat_input)
        input_row.addWidget(self.send_button)
        layout.addLayout(input_row)

        self._history: list[dict] = []
        self._waiting_for_response = False

        self.brain_service = BrainService(parent=self)
        self.brain_service.response_ready.connect(self._on_brain_response)
        self.brain_service.error_occurred.connect(self._on_brain_error)

        self._add_message(BRAIN_GREETING, is_user=False)

    def _add_message(self, text: str, is_user: bool):
        row = _build_message_row(text, is_user)
        self.messages_layout.insertWidget(self.messages_layout.count() - 1, row)
        QTimer.singleShot(0, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_send_clicked(self):
        if self._waiting_for_response:
            return
        text = self.chat_input.toPlainText().strip()
        if not text:
            return

        self._add_message(text, is_user=True)
        self.chat_input.clear()
        self._history.append({"role": "user", "content": text})

        self._set_waiting(True)
        self.brain_service.send_message(list(self._history))

    def _on_brain_response(self, text: str):
        self._history.append({"role": "assistant", "content": text})
        self._add_message(text, is_user=False)
        self._set_waiting(False)

    def _on_brain_error(self, message: str):
        self._add_message(f"Brain 응답 중 오류가 발생했습니다: {message}", is_user=False)
        self._set_waiting(False)

    def _set_waiting(self, waiting: bool):
        self._waiting_for_response = waiting
        self.send_button.setEnabled(not waiting)
