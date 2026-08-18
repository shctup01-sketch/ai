from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai.brain_response import BrainResponse
from chat_panel import ChatPanel

DARK_STYLE = """
QWidget {
    background-color: #1e1e1e;
    color: #e0e0e0;
    font-size: 13px;
}
QMainWindow {
    background-color: #1e1e1e;
}
#TopBar {
    background-color: #252526;
    border-bottom: 1px solid #3a3a3a;
}
#TopBarTitle {
    font-size: 16px;
    font-weight: bold;
    letter-spacing: 2px;
    padding: 10px;
}
#LeftPanel, #RightPanel {
    background-color: #232324;
}
#SectionLabel {
    font-weight: bold;
    color: #9cdcfe;
    padding-top: 8px;
}
#CenterPrompt {
    font-size: 15px;
    font-weight: bold;
    padding: 6px 0;
}
#CenterSubtitle {
    font-size: 12px;
    color: #9a9a9a;
    padding-bottom: 6px;
}
#ChatScrollArea {
    border: none;
}
#UserBubble {
    background-color: #2b5278;
    border-radius: 8px;
    padding: 8px 10px;
}
#BrainBubble {
    background-color: #2d2d30;
    border-radius: 8px;
    padding: 8px 10px;
}
QListWidget, QTextEdit, QLineEdit {
    background-color: #1e1e1e;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    padding: 4px;
}
QPushButton {
    background-color: #2d2d30;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
    padding: 6px;
}
QPushButton:hover:!disabled {
    background-color: #37373d;
}
QPushButton:disabled {
    color: #6a6a6a;
}
.StatusBadge {
    color: #d7ba7d;
}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI Development Studio")
        self.resize(1100, 700)
        self.setStyleSheet(DARK_STYLE)

        self._current_plan: BrainResponse | None = None

        central_widget = QWidget()
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_top_bar())

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)
        content_layout.addWidget(self._build_left_panel())
        content_layout.addWidget(self._build_center_panel(), stretch=1)
        content_layout.addWidget(self._build_right_panel())
        root_layout.addLayout(content_layout)

        self.setCentralWidget(central_widget)

    def _build_top_bar(self) -> QWidget:
        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        layout = QHBoxLayout(top_bar)
        title = QLabel("AI DEVELOPMENT STUDIO")
        title.setObjectName("TopBarTitle")
        layout.addWidget(title)
        return top_bar

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("LeftPanel")
        panel.setFixedWidth(220)
        layout = QVBoxLayout(panel)

        projects_label = QLabel("PROJECTS")
        projects_label.setObjectName("SectionLabel")
        layout.addWidget(projects_label)

        self.project_list = QListWidget()
        layout.addWidget(self.project_list)

        new_project_button = QPushButton("+ 새 프로젝트")
        new_project_button.clicked.connect(self._on_new_project_clicked)
        layout.addWidget(new_project_button)

        ai_team_label = QLabel("AI TEAM")
        ai_team_label.setObjectName("SectionLabel")
        layout.addWidget(ai_team_label)

        for ai_name in ("Brain (총괄 두뇌)", "Reviewer (검토 AI)", "Developer (개발 AI)"):
            layout.addLayout(self._build_ai_status_row(ai_name))

        layout.addStretch(1)
        return panel

    def _build_ai_status_row(self, name: str) -> QHBoxLayout:
        row = QHBoxLayout()
        name_label = QLabel(name)
        status_label = QLabel("대기")
        status_label.setProperty("class", "StatusBadge")
        status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(name_label)
        row.addWidget(status_label)
        return row

    def _build_center_panel(self) -> QWidget:
        self.chat_panel = ChatPanel()
        self.chat_panel.plan_ready.connect(self._on_plan_ready)
        return self.chat_panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("RightPanel")
        panel.setFixedWidth(220)
        layout = QVBoxLayout(panel)

        status_label = QLabel("WORK STATUS")
        status_label.setObjectName("SectionLabel")
        layout.addWidget(status_label)

        layout.addWidget(QLabel("현재 작업"))
        self.current_task_value_label = QLabel("대기 중")
        layout.addWidget(self.current_task_value_label)
        layout.addWidget(QLabel("작업 단계"))
        self.work_step_value_label = QLabel("아직 시작된 작업 없음")
        layout.addWidget(self.work_step_value_label)

        layout.addStretch(1)

        self.plan_button = QPushButton("작업 계획")
        self.plan_button.setEnabled(False)
        self.plan_button.clicked.connect(self._on_plan_button_clicked)
        develop_button = QPushButton("개발 실행")
        develop_button.setEnabled(False)
        layout.addWidget(self.plan_button)
        layout.addWidget(develop_button)

        return panel

    def _on_new_project_clicked(self):
        count = self.project_list.count() + 1
        self.project_list.addItem(f"새 프로젝트 {count}")

    def _on_plan_ready(self, plan: BrainResponse):
        self._current_plan = plan
        self.current_task_value_label.setText(plan.project_name or "")
        self.work_step_value_label.setText("계획 완료")
        self.plan_button.setEnabled(True)

    def _on_plan_button_clicked(self):
        if self._current_plan is None:
            return

        plan = self._current_plan
        features = "\n".join(f"- {item}" for item in (plan.feature_list or []))
        steps = "\n".join(f"{i}. {item}" for i, item in enumerate(plan.task_steps or [], start=1))

        message = (
            f"프로젝트 이름\n{plan.project_name or '(없음)'}\n\n"
            f"요구사항 요약\n{plan.requirements_summary or '(없음)'}\n\n"
            f"기능 목록\n{features or '(없음)'}\n\n"
            f"작업 단계\n{steps or '(없음)'}"
        )

        QMessageBox.information(self, "작업 계획", message)
