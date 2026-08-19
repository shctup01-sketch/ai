from pathlib import Path

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
from ai.developer_fix_request import DeveloperFixRequest
from ai.developer_request import DeveloperRequest
from ai.developer_result import DeveloperResult
from ai.developer_service import DeveloperService
from ai.execution_result import ExecutionResult
from ai.execution_service import ExecutionService
from ai.package_fix_service import PackageFixService
from chat_panel import ChatPanel
from project_runner import EntryPointError, resolve_entry_point
from project_venv import find_unsafe_requirements, parse_requirements

# 한 번의 "프로그램 실행" 시도 동안 사용자가 "AI에게 수정 요청"을 누를 수
# 있는 최대 횟수. 자동으로 반복 실행되지 않고, 매번 사용자가 다시 눌러야
# 다음 시도가 시작된다.
MAX_PACKAGE_FIX_ATTEMPTS = 2

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
        self._current_developer_result: DeveloperResult | None = None
        self._package_fix_attempts = 0

        self.developer_service = DeveloperService(parent=self)
        self.developer_service.result_ready.connect(self._on_developer_result)
        self.developer_service.error_occurred.connect(self._on_developer_error)

        self.execution_service = ExecutionService(parent=self)
        self.execution_service.result_ready.connect(self._on_execution_result)
        self.execution_service.error_occurred.connect(self._on_execution_error)
        self.execution_service.stage_changed.connect(self._on_execution_stage_changed)

        self.package_fix_service = PackageFixService(parent=self)
        self.package_fix_service.result_ready.connect(self._on_package_fix_result)
        self.package_fix_service.error_occurred.connect(self._on_package_fix_error)

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
        if name.startswith("Developer"):
            self.developer_status_label = status_label
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
        self.develop_button = QPushButton("개발 실행")
        self.develop_button.setEnabled(False)
        self.develop_button.clicked.connect(self._on_develop_button_clicked)
        self.execute_button = QPushButton("프로그램 실행")
        self.execute_button.setEnabled(False)
        self.execute_button.clicked.connect(self._on_execute_button_clicked)
        layout.addWidget(self.plan_button)
        layout.addWidget(self.develop_button)
        layout.addWidget(self.execute_button)

        return panel

    def _on_new_project_clicked(self):
        count = self.project_list.count() + 1
        self.project_list.addItem(f"새 프로젝트 {count}")

    def _on_plan_ready(self, plan: BrainResponse):
        self._current_plan = plan
        self._current_developer_result = None
        self._package_fix_attempts = 0
        self.current_task_value_label.setText(plan.project_name or "")
        self.work_step_value_label.setText("계획 완료")
        self.plan_button.setEnabled(True)
        self.develop_button.setEnabled(True)
        self.execute_button.setEnabled(False)

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

    def _on_develop_button_clicked(self):
        if self._current_plan is None:
            return

        self.develop_button.setEnabled(False)
        self.developer_status_label.setText("작업 중")
        self.work_step_value_label.setText("개발 중")

        plan = self._current_plan
        request = DeveloperRequest(
            project_name=plan.project_name or "새 프로젝트",
            requirements_summary=plan.requirements_summary or "",
            feature_list=plan.feature_list or [],
            task_steps=plan.task_steps or [],
        )
        self.developer_service.build_project(request)

    def _on_developer_result(self, result: DeveloperResult):
        self.develop_button.setEnabled(True)

        if result.status == "success":
            self.developer_status_label.setText("완료")
            self.work_step_value_label.setText("개발 완료")
            self._current_developer_result = result
            self._package_fix_attempts = 0
            self.execute_button.setEnabled(True)
            self._show_developer_result_popup(result)
        else:
            self.developer_status_label.setText("오류")
            self.work_step_value_label.setText("개발 오류")
            self._current_developer_result = None
            self.execute_button.setEnabled(False)
            error_text = "\n".join(result.errors) if result.errors else result.summary
            QMessageBox.warning(self, "개발 실패", error_text)

    def _on_developer_error(self, message: str):
        self.develop_button.setEnabled(True)
        self.developer_status_label.setText("오류")
        self.work_step_value_label.setText("개발 오류")
        QMessageBox.warning(self, "개발 실패", message)

    def _show_developer_result_popup(self, result: DeveloperResult):
        project_name = self._current_plan.project_name if self._current_plan else ""
        files_text = "\n".join(f"- {name}" for name in result.created_files) or "(없음)"

        message = (
            f"프로젝트:\n{project_name}\n\n"
            f"저장 위치:\n{result.project_path}\n\n"
            f"생성된 파일:\n{files_text}"
        )
        QMessageBox.information(self, "개발 완료", message)

    def _on_execute_button_clicked(self):
        if self._current_developer_result is None:
            return

        # 사용자가 직접 "프로그램 실행"을 눌러 새로 시작하는 시도이므로,
        # 이전 시도에서 쌓인 AI 패키지 수정 횟수를 여기서 초기화한다.
        # (AI 수정 이후 자동으로 이어지는 재실행에서는 이 메서드를 거치지
        # 않고 _run_project()를 직접 호출하므로 횟수가 유지된다.)
        self._package_fix_attempts = 0

        project_path = Path(self._current_developer_result.project_path)
        self._run_project(project_path, self._current_developer_result.entry_point)

    def _run_project(self, project_path: Path, entry_point_str: str):
        """entry_point 검증 → requirements 보안 검사 → 설치 승인 → 실행.

        최초 실행과, AI 패키지 수정 이후 재실행이 모두 이 메서드를
        공유한다. 실제 설치/실행은 항상 기존 ExecutionService를 통해서만
        이뤄진다 — MainWindow가 pip나 subprocess를 직접 다루지 않는다.
        """
        try:
            entry_point = resolve_entry_point(project_path, entry_point_str)
        except EntryPointError:
            QMessageBox.warning(
                self,
                "실행 불가",
                "프로그램 실행 파일을 확인할 수 없습니다.",
            )
            return

        requirements_path = project_path / "requirements.txt"
        install_requirements_flag = False

        if requirements_path.exists():
            requirement_lines = parse_requirements(requirements_path.read_text(encoding="utf-8"))

            if requirement_lines:
                unsafe_lines = find_unsafe_requirements(requirement_lines)
                if unsafe_lines:
                    unsafe_text = "\n".join(f"- {line}" for line in unsafe_lines)
                    QMessageBox.warning(
                        self,
                        "실행 불가",
                        "requirements.txt에 안전하지 않은 항목이 있어 설치할 수 없습니다:\n\n"
                        f"{unsafe_text}",
                    )
                    return

                package_text = "\n".join(f"- {line}" for line in requirement_lines)
                answer = QMessageBox.question(
                    self,
                    "패키지 설치 확인",
                    "다음 패키지를 프로젝트 전용 가상환경에 설치한 뒤 실행합니다:\n\n"
                    f"{package_text}\n\n계속하시겠습니까?",
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return

                install_requirements_flag = True

        self.execute_button.setEnabled(False)
        self.developer_status_label.setText("작업 중")
        self.work_step_value_label.setText("실행 준비 중")

        self.execution_service.run_project(project_path, entry_point, install_requirements_flag)

    def _on_execution_stage_changed(self, stage: str):
        self.work_step_value_label.setText(stage)

    def _on_execution_result(self, result: ExecutionResult):
        self.execute_button.setEnabled(True)

        if result.status == "success":
            self.developer_status_label.setText("완료")
            self.work_step_value_label.setText("실행 완료")
            self._show_execution_result_popup(result, title="실행 완료")
            return

        self.developer_status_label.setText("오류")
        self.work_step_value_label.setText("실행 오류")

        # AI 수정 요청은 "패키지 설치" 단계 실패에서만 제공한다. main.py
        # 실행 자체가 실패한 일반 runtime 오류는 이 기능과 연결하지 않는다.
        if result.stage == "package_install" and self._package_fix_attempts < MAX_PACKAGE_FIX_ATTEMPTS:
            self._offer_package_fix(result)
        else:
            self._show_execution_result_popup(result, title="실행 실패")
            if result.stage == "package_install":
                QMessageBox.information(
                    self,
                    "안내",
                    "AI 패키지 수정 최대 시도 횟수에 도달했습니다.",
                )

    def _on_execution_error(self, message: str):
        self.execute_button.setEnabled(True)
        self.developer_status_label.setText("오류")
        self.work_step_value_label.setText("실행 오류")
        QMessageBox.warning(self, "실행 실패", message)

    def _show_execution_result_popup(self, result: ExecutionResult, title: str):
        parts = [result.summary]
        if result.return_code is not None:
            parts.append(f"종료 코드: {result.return_code}")
        if result.stdout:
            parts.append(f"표준 출력:\n{result.stdout}")
        if result.stderr:
            parts.append(f"표준 오류:\n{result.stderr}")

        message = "\n\n".join(parts)
        if result.status == "success":
            QMessageBox.information(self, title, message)
        else:
            QMessageBox.warning(self, title, message)

    def _offer_package_fix(self, result: ExecutionResult):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("패키지 설치 실패")
        box.setText(result.summary)
        if result.stderr:
            box.setDetailedText(result.stderr)
        box.addButton("닫기", QMessageBox.ButtonRole.RejectRole)
        fix_button = box.addButton("AI에게 수정 요청", QMessageBox.ButtonRole.AcceptRole)
        box.exec()

        if box.clickedButton() is fix_button:
            self._start_package_fix(result)

    def _start_package_fix(self, failed_result: ExecutionResult):
        if self._current_developer_result is None:
            return

        self._package_fix_attempts += 1

        project_path = Path(self._current_developer_result.project_path)
        requirements_path = project_path / "requirements.txt"
        requirements_text = (
            requirements_path.read_text(encoding="utf-8") if requirements_path.exists() else ""
        )

        request = DeveloperFixRequest(
            project_name=self._current_plan.project_name if self._current_plan else "",
            entry_point=self._current_developer_result.entry_point,
            requirements_text=requirements_text,
            pip_stderr=failed_result.stderr,
        )

        self.execute_button.setEnabled(False)
        self.developer_status_label.setText("작업 중")
        self.work_step_value_label.setText("AI 패키지 수정 중")

        self.package_fix_service.fix_packages(project_path, request)

    def _on_package_fix_result(self, result: DeveloperResult):
        if result.status != "success":
            self.execute_button.setEnabled(True)
            self.developer_status_label.setText("오류")
            self.work_step_value_label.setText("AI 패키지 수정 실패")
            error_text = "\n".join(result.errors) if result.errors else result.summary
            QMessageBox.warning(self, "AI 패키지 수정 실패", error_text)
            return

        # Developer가 파일을 수정했으므로 최신 상태(entry_point, 생성/수정된
        # 파일 목록 등)로 갱신한다. 실제 재설치/재실행은 기존 승인 흐름을
        # 그대로 타야 하므로 여기서 곧바로 pip를 실행하지 않는다.
        self._current_developer_result = result
        self.developer_status_label.setText("완료")
        self.work_step_value_label.setText("AI 패키지 수정 완료")

        project_path = Path(result.project_path)
        self._run_project(project_path, result.entry_point)

    def _on_package_fix_error(self, message: str):
        self.execute_button.setEnabled(True)
        self.developer_status_label.setText("오류")
        self.work_step_value_label.setText("AI 패키지 수정 실패")
        QMessageBox.warning(self, "AI 패키지 수정 실패", message)
