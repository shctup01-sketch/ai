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

from ai.brain_response import BrainResponse
from ai.chief_brain_compat import ChiefBrainCompatError, adapt_chief_brain_plan_to_brain_response
from ai.chief_brain_plan import ChiefBrainPlan
from ai.chief_brain_service import ChiefBrainService

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

        # 사용자 입력의 1차 판단자는 Chief Brain이다(23단계) - 기존
        # BrainService/OpenAIProvider는 삭제하지 않고 남겨두지만, 이 화면은
        # 더 이상 그것을 직접 호출하지 않는다. 단일 development/research
        # 요청은 chief_brain_compat.py를 거쳐 기존 UI 흐름 그대로 재사용한다.
        self.chief_brain_service = ChiefBrainService(parent=self)
        self.chief_brain_service.plan_ready.connect(self._on_chief_brain_plan_ready)
        self.chief_brain_service.error_occurred.connect(self._on_brain_error)

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
