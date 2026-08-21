import os
import uuid
from pathlib import Path

from openai import OpenAI
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ai import image_content, screen_capture
from ai.analysis_executor import AnalysisExecutor
from ai.brain_response import BrainResponse
from ai.brain_task_step import BrainTaskStep
from ai.checkpoint_context import describe_step_result, find_latest_step_result
from ai.project_stage_rerun import (
    build_rerun_candidate_completed_steps,
    compute_affected_step_ids,
    find_rerun_root_step_ids,
)
from ai.chief_brain_orchestrator import ChiefBrainOrchestrator
from ai.chief_brain_plan import ChiefBrainPlan
from ai.developer_fix_request import DeveloperFixRequest
from ai.developer_request import DeveloperRequest
from ai.developer_result import DeveloperResult
from ai.developer_service import DeveloperService
from ai.development_executor import DevelopmentExecutor
from ai.development_revision_executor import DevelopmentRevisionExecutor
from ai.development_revision_plan import DevelopmentRevisionPlan
from ai.development_revision_request import DevelopmentRevisionRequest
from ai.development_revision_service import DevelopmentRevisionService
from ai.development_revision_summary import DevelopmentRevisionSummary, build_revision_summary
from ai.execution_result import ExecutionResult
from ai.execution_service import ExecutionService
from ai.openai_developer_provider import OpenAIDeveloperProvider
from ai.openai_development_revision_provider import OpenAIDevelopmentRevisionProvider
from ai.openai_research_reviewer_provider import OpenAIResearchReviewerProvider
from ai.openai_screen_observation_provider import OpenAIScreenObservationProvider
from ai.orchestration_result import OrchestrationResult
from ai.orchestration_service import OrchestrationService
from ai.orchestration_step_result import OrchestrationStepResult
from ai.package_fix_service import PackageFixService
from ai.project_state import PersistentProjectState, create_project_state
from ai.project_state_store import ProjectStateError, ProjectStateStore
from ai.research_review_request import ResearchReviewRequest
from ai.research_review_result import ResearchReviewResult
from ai.research_review_service import ResearchReviewService
from ai.screen_observation_executor import ScreenObservationExecutor
from ai.screen_observation_result import ScreenObservationResult
from ai.screen_observation_service import ScreenObservationService
from ai.task import Task
from ai.task_execution_service import TaskExecutionService
from ai.task_system import TaskSystem
from chat_panel import ChatPanel, _encode_image_to_png_bytes
from project_runner import EntryPointError, resolve_entry_point
from project_venv import find_unsafe_requirements, parse_requirements
from workspace_guard import WorkspaceGuard

# 한 번의 "프로그램 실행" 시도 동안 사용자가 "AI에게 수정 요청"을 누를 수
# 있는 최대 횟수. 자동으로 반복 실행되지 않고, 매번 사용자가 다시 눌러야
# 다음 시도가 시작된다.
MAX_PACKAGE_FIX_ATTEMPTS = 2

# Chief Brain이 승인을 요청하는 화면 확인 step의 task_type(29단계).
# chief_brain_instructions.py가 LLM에게 가르치는 값과 정확히 같아야 한다.
_SCREEN_OBSERVATION_TASK_TYPE = "screen_observation"

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
#PendingImageItem {
    background-color: #252526;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
}
#PendingFileItem {
    background-color: #252526;
    border: 1px solid #3a3a3a;
    border-radius: 4px;
}
#PasteStatusLabel {
    padding: 2px 0;
}
#AttachButton {
    font-weight: bold;
}
#ScreenCaptureButton {
    font-size: 11px;
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
        self._current_task: Task | None = None

        # research 기능을 실제로 쓸 때만 지연 생성한다(_ensure_task_system).
        # 개발 기능만 쓰는 사용자가 OpenAI API Key 문제로 시작부터 영향받지
        # 않도록 하기 위함이다.
        self.task_system: TaskSystem | None = None
        self.task_execution_service: TaskExecutionService | None = None

        # Reviewer(조사 결과 분석)도 research와 동일하게 실제로 쓸 때만
        # 지연 생성한다(_ensure_research_review_service).
        self.research_review_service: ResearchReviewService | None = None
        self._current_research_review_result: ResearchReviewResult | None = None

        # 복합 업무(step 2개 이상, 또는 development/research가 아닌 단일
        # task_type)는 기존 BrainResponse로 표현할 수 없으므로 별도 상태로
        # 보관한다. Orchestrator도 실제로 쓸 때만 지연 생성한다
        # (_ensure_orchestration_service).
        self._current_chief_plan: ChiefBrainPlan | None = None
        self.orchestration_service: OrchestrationService | None = None
        # 직전 run()/resume() 결과를 보관한다 - screen_observation 승인 후
        # resume()을 호출할 때 "이미 완료된 step들"을 다시 실행하지 않고
        # 그대로 이어붙이기 위해 필요하다(29단계).
        self._last_orchestration_result: OrchestrationResult | None = None

        # Screen Observation(29단계) - 사용자가 승인 Dialog에서 "화면 공유
        # 승인"을 눌렀을 때만 지연 생성한다. 승인 대기 중인 BrainTaskStep을
        # 잠시 들고 있다가, Fake가 아닌 실제 화면 분석 결과가 오면 그
        # step과 짝지어 resume()에 넘긴다.
        self.screen_observation_service: ScreenObservationService | None = None
        self._pending_screen_observation_step: BrainTaskStep | None = None

        # 37단계 - 개발 결과 실행 검토("실행해서 확인") 전용
        # ExecutionService/ScreenObservationService. 기존 execute_button
        # 흐름(execution_service)/screen_observation 승인 흐름
        # (screen_observation_service)과 완전히 분리된 별도 인스턴스로만
        # 지연 생성한다 - 같은 인스턴스를 재사용하면 거기 이미 연결된
        # 기존 슬롯도 함께 호출되어 서로 다른 흐름이 뒤섞인다(같은
        # 클래스/계약은 재사용하되 인스턴스는 분리, §3/§8/§16).
        self.review_execution_service: ExecutionService | None = None
        self.review_screen_observation_service: ScreenObservationService | None = None
        self._runtime_review_step: BrainTaskStep | None = None
        self._runtime_review_dev_result: DeveloperResult | None = None
        self._runtime_review_plan: ChiefBrainPlan | None = None
        self._runtime_review_execution_result: ExecutionResult | None = None
        self._runtime_review_image_pixmap: QPixmap | None = None

        # 38단계 - "수정 요청" 실제 처리("수정 요청 -> Brain 재계획 ->
        # Developer 재작업 -> 다시 waiting_for_review"). 여기서도 37단계와
        # 동일한 이유로 기존 orchestration_service/screen_observation_service
        # 등과 완전히 분리된 전용 인스턴스만 지연 생성한다. revision_plan은
        # 승인 이후 실제로 실행하는 임시 ChiefBrainPlan(execution_mode=
        # "project")이다 - 원래 project plan(self._current_chief_plan)의
        # steps는 절대 건드리지 않는다(§8).
        self.development_revision_service: DevelopmentRevisionService | None = None
        self.revision_orchestration_service: OrchestrationService | None = None
        self._revision_original_step: BrainTaskStep | None = None
        self._revision_original_dev_result: DeveloperResult | None = None
        self._revision_original_plan: ChiefBrainPlan | None = None
        self._revision_plan: ChiefBrainPlan | None = None

        # 39단계 - 수정 전/후 변경 요약. before_files/user_request_text는
        # 이번 revision 시작 시점에 채워지고, last_summary는 그 revision이
        # 성공했을 때만 채워진다 - 다음 revision이 시작되면 그때 다시
        # 덮어써질 뿐, 새 project development step(수정이 아닌 원래
        # 단계)의 첫 검토 화면(_handle_development_review)에서는 이전
        # revision의 요약이 섞이지 않도록 명시적으로 비운다(§10).
        self._revision_before_files: list[str] | None = None
        self._revision_user_request_text: str | None = None
        self._revision_last_summary: DevelopmentRevisionSummary | None = None

        # 40단계 - revision 전/후 실제 실행 화면 비교. before는 이번
        # revision을 "시작하는 시점"에 마지막으로 보고 있던 화면/분석을
        # 그대로 승격한 것이고(§4/§11 - 다음 revision에서는 지금의
        # after가 다음 before가 된다), after는 그 revision이 끝난 뒤
        # 사용자가 다시 "실행해서 확인"을 눌러 얻은 최신 화면/분석이다.
        # v1은 현재 revision 하나에 대한 before/after 2개만 유지한다
        # (§13 - 무한 누적 금지, 디스크 저장 없이 세션 메모리에만 둔다).
        self._revision_before_image: QPixmap | None = None
        self._revision_before_observation: ScreenObservationResult | None = None
        self._revision_after_image: QPixmap | None = None
        self._revision_after_observation: ScreenObservationResult | None = None

        # 41단계 - 장기 project 진행 상태 저장/불러오기. project_state_store는
        # 순수 Python(JSON 파일)만 다루고 API Key/OpenAI client가 전혀
        # 필요 없으므로 다른 서비스들과 달리 지연 생성 없이 바로 만든다.
        # _active_project_*는 execution_mode == "project"인 계획이 준비된
        # 이후에만 채워진다(§12 - task 모드는 장기 프로젝트 저장 대상이
        # 아니다).
        self.project_state_store = ProjectStateStore()
        self._active_project_id: str | None = None
        self._active_project_name: str | None = None
        self._active_project_created_at: str | None = None

        # 45단계 - 저장된 장기 project의 완료된 research(와 그에 의존하는
        # analysis/development)를 최신 코드로 다시 실행하기 위한 전용
        # OrchestrationService. 37/38단계와 동일한 이유로 원래 project
        # plan 실행에 쓰는 orchestration_service와 완전히 분리된 인스턴스로만
        # 지연 생성한다 - 성공하기 전까지는 self._last_orchestration_result/
        # 영구 저장을 전혀 건드리지 않는다(§5/§15, 아래 핸들러 참고).
        self.rerun_orchestration_service: OrchestrationService | None = None

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

        # 32단계 - 4개 행 모두 상태 label을 self 속성으로 저장한다(기존
        # Developer만 저장하던 방식을 일반화 - developer_status_label을
        # 쓰는 기존 단일 development/실행/PackageFix 코드는 속성 이름이
        # 그대로라 전혀 바뀌지 않는다).
        for name, attr_name in (
            ("Chief Brain (총괄 두뇌)", "chief_brain_status_label"),
            ("Research (조사 AI)", "research_status_label"),
            ("Analysis (분석 AI)", "analysis_status_label"),
            ("Developer (개발 AI)", "developer_status_label"),
        ):
            layout.addLayout(self._build_ai_status_row(name, attr_name))

        layout.addStretch(1)
        return panel

    def _build_ai_status_row(self, name: str, attr_name: str) -> QHBoxLayout:
        row = QHBoxLayout()
        name_label = QLabel(name)
        status_label = QLabel("대기")
        status_label.setProperty("class", "StatusBadge")
        status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row.addWidget(name_label)
        row.addWidget(status_label)
        setattr(self, attr_name, status_label)
        return row

    def _build_center_panel(self) -> QWidget:
        self.chat_panel = ChatPanel()
        self.chat_panel.plan_ready.connect(self._on_plan_ready)
        self.chat_panel.chief_plan_ready.connect(self._on_chief_plan_ready)
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
        # "프로그램 실행"은 Developer가 만든 Python 프로그램 실행 전용이다.
        # research Task 실행은 이 버튼을 재사용하지 않고 별도 버튼을 쓴다.
        self.task_execute_button = QPushButton("작업 실행")
        self.task_execute_button.setEnabled(False)
        self.task_execute_button.clicked.connect(self._on_task_execute_button_clicked)
        # "업무 실행"은 복합 ChiefBrainPlan(step 2개 이상 등) 전용이다 -
        # 단일 development/research는 기존 버튼들을 그대로 쓴다.
        self.chief_plan_execute_button = QPushButton("업무 실행")
        self.chief_plan_execute_button.setEnabled(False)
        self.chief_plan_execute_button.clicked.connect(self._on_chief_plan_execute_button_clicked)
        layout.addWidget(self.plan_button)
        layout.addWidget(self.develop_button)
        layout.addWidget(self.execute_button)
        layout.addWidget(self.task_execute_button)
        layout.addWidget(self.chief_plan_execute_button)

        # 41단계 §13 - 대형 Project Manager가 아니라 최소 저장/불러오기
        # 버튼 2개만 기존 WORK STATUS 패널에 추가한다(새 UI 영역을 만들지
        # 않는다).
        self.save_project_button = QPushButton("프로젝트 저장")
        self.save_project_button.clicked.connect(self._on_save_project_button_clicked)
        self.load_project_button = QPushButton("프로젝트 불러오기")
        self.load_project_button.clicked.connect(self._on_load_project_button_clicked)
        layout.addWidget(self.save_project_button)
        layout.addWidget(self.load_project_button)

        # 45단계 §18 - 대형 Project Manager/편집기가 아니라 최소 버튼
        # 하나만 기존 저장/불러오기 버튼 옆에 추가한다.
        self.rerun_research_analysis_button = QPushButton("조사/분석 다시 실행")
        self.rerun_research_analysis_button.clicked.connect(self._on_rerun_research_analysis_button_clicked)
        layout.addWidget(self.rerun_research_analysis_button)

        return panel

    def _on_new_project_clicked(self):
        count = self.project_list.count() + 1
        self.project_list.addItem(f"새 프로젝트 {count}")

    def _on_plan_ready(self, plan: BrainResponse):
        self._current_plan = plan
        self._current_developer_result = None
        self._package_fix_attempts = 0
        self._current_task = None
        self._current_research_review_result = None
        self._current_chief_plan = None

        self.plan_button.setEnabled(True)
        self.develop_button.setEnabled(False)
        self.execute_button.setEnabled(False)
        self.task_execute_button.setEnabled(False)
        self.chief_plan_execute_button.setEnabled(False)

        if plan.task_type == "development":
            self.current_task_value_label.setText(plan.project_name or "")
            self.work_step_value_label.setText("계획 완료")
            self.develop_button.setEnabled(True)
        elif plan.task_type == "research":
            self.current_task_value_label.setText(plan.research_title or "")
            self.work_step_value_label.setText("계획 완료")

            task_system = self._ensure_task_system()
            if task_system is None:
                return

            task = task_system.create_task(
                task_type="research",
                title=plan.research_title or "",
                goal=plan.research_goal or "",
            )
            self._current_task = task
            self.task_execute_button.setEnabled(True)

    def _on_chief_plan_ready(self, plan: ChiefBrainPlan):
        """복합 업무(step 2개 이상, 또는 기존 BrainResponse로 표현할 수 없는
        단일 task_type)가 준비되면 호출된다. 단일 development/research는
        ChatPanel이 이미 기존 plan_ready(BrainResponse) 경로로 처리하므로
        여기까지 오지 않는다.
        """
        self._current_chief_plan = plan
        self._current_plan = None
        self._current_developer_result = None
        self._package_fix_attempts = 0
        self._current_task = None
        self._current_research_review_result = None

        self.plan_button.setEnabled(False)
        self.develop_button.setEnabled(False)
        self.execute_button.setEnabled(False)
        self.task_execute_button.setEnabled(False)
        self.chief_plan_execute_button.setEnabled(True)

        self.current_task_value_label.setText(plan.objective or "")
        # 33단계 - 기존 WORK STATUS 영역을 그대로 재사용해 실행 모드만
        # 덧붙인다(새 UI 요소를 추가하지 않는다). execution_mode가 없는
        # 기존 Fake/구버전 응답도 ChiefBrainPlan 기본값("task")으로
        # 안전하게 처리된다.
        if plan.execution_mode == "project":
            self.work_step_value_label.setText("업무 계획 완료 (대형 프로젝트)")
        else:
            self.work_step_value_label.setText("업무 계획 완료")

        # 32단계 - 복합 업무 실행 때만 필요한 AI TEAM 상태 초기화(5단계).
        # 단일 development/research/Reviewer 흐름은 이 핸들러를 거치지
        # 않으므로 여기서 초기화해도 그쪽에는 영향이 없다.
        self.chief_brain_status_label.setText("계획 완료")
        self.research_status_label.setText("대기")
        self.analysis_status_label.setText("대기")
        self.developer_status_label.setText("대기")

        # 41단계 §11/§12 - project 모드 계획이 막 확정된 시점("project
        # plan 생성 완료")도 저장 지점 중 하나다. task 모드는 장기 프로젝트
        # 저장 대상이 아니므로 여기서 완전히 제외한다(_active_project_id를
        # 만들지 않는다 - 이후 _on_orchestration_result의 저장 훅도
        # _active_project_id가 None이면 아무 것도 하지 않는다).
        if plan.execution_mode == "project":
            self._active_project_id = str(uuid.uuid4())
            self._active_project_name = plan.objective
            self._active_project_created_at = None
            self._save_active_project_state()
        else:
            self._active_project_id = None
            self._active_project_name = None
            self._active_project_created_at = None

    def _on_plan_button_clicked(self):
        if self._current_plan is None:
            return

        plan = self._current_plan

        if plan.task_type == "research":
            message = (
                f"조사 제목\n{plan.research_title or '(없음)'}\n\n"
                f"조사 목표\n{plan.research_goal or '(없음)'}"
            )
            QMessageBox.information(self, "작업 계획", message)
            return

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

    def _ensure_task_system(self) -> TaskSystem | None:
        """research 기능을 실제로 쓸 때만 TaskSystem을 지연 생성한다.

        Brain(OpenAIProvider)과 동일한 방식으로 OPENAI_API_KEY를 읽어 OpenAI
        client를 만들고, 그 client를 TaskSystem에 그대로 주입한다.
        TaskSystem 내부에서는 API Key를 다시 읽지 않는다.
        """
        if self.task_system is not None:
            return self.task_system

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            QMessageBox.warning(
                self,
                "조사 실행 불가",
                "OpenAI API Key가 설정되지 않았습니다. "
                "프로젝트 루트의 .env 파일에 OPENAI_API_KEY 값을 입력한 뒤 다시 시도해주세요.",
            )
            return None

        client = OpenAI(api_key=api_key)
        self.task_system = TaskSystem(client)
        self.task_execution_service = TaskExecutionService(self.task_system, parent=self)
        self.task_execution_service.result_ready.connect(self._on_task_execution_result)
        self.task_execution_service.error_occurred.connect(self._on_task_execution_error)
        return self.task_system

    def _on_task_execute_button_clicked(self):
        if self._current_task is None or self.task_execution_service is None:
            return

        self.task_execute_button.setEnabled(False)
        self.work_step_value_label.setText("조사 중")

        self.task_execution_service.execute_task(self._current_task.task_id)

    def _on_task_execution_result(self, task: Task):
        self.task_execute_button.setEnabled(True)
        self._current_task = task

        if task.status == "success":
            self._start_research_review(task)
        else:
            self.work_step_value_label.setText("조사 오류")
            error_text = "\n".join(task.errors) if task.errors else "조사 중 오류가 발생했습니다."
            QMessageBox.warning(self, "조사 실패", error_text)

    def _on_task_execution_error(self, message: str):
        self.task_execute_button.setEnabled(True)
        self.work_step_value_label.setText("조사 오류")
        QMessageBox.warning(self, "조사 실패", message)

    def _show_scrollable_result_dialog(self, title: str, content: str):
        """긴 텍스트 결과(조사 결과/분석 결과 등)를 스크롤 가능한 창으로 보여준다.

        QMessageBox는 내용이 화면 높이를 넘어가면 아래쪽을 볼 방법이 없어서
        (Windows 실기에서 확인된 문제) 대신 크기 조절 가능한 QDialog +
        읽기 전용 텍스트 영역을 쓴다. 조사 결과 전용이 아니라, 앞으로 다른
        긴 텍스트 결과(사업 분석/보고서 등)에도 그대로 재사용할 수 있게
        일반적인 (title, content) 형태로 만든다.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(title)

        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            max_width = max(1, int(available.width() * 0.8))
            max_height = max(1, int(available.height() * 0.85))
        else:
            max_width, max_height = 850, 750

        default_width = min(800, max_width)
        default_height = min(650, max_height)

        # setFixedSize를 쓰지 않는다 - 사용자가 모서리를 드래그해 창 크기를
        # 조절할 수 있어야 한다(고정 크기 Dialog 금지). resize()는 초기
        # 크기만 정할 뿐 크기 조절 가능 여부와는 무관하다.
        dialog.resize(default_width, default_height)
        dialog.setMaximumSize(max_width, max_height)

        layout = QVBoxLayout(dialog)

        title_label = QLabel(title, dialog)
        layout.addWidget(title_label)

        text_edit = QPlainTextEdit(dialog)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(content)
        layout.addWidget(text_edit, stretch=1)

        close_button = QPushButton("닫기", dialog)
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)

        dialog.exec()

    def _show_research_result_popup(self, task: Task):
        result = task.result or {}
        query = result.get("query", "")
        search_results = result.get("search_results", [])

        if search_results:
            results_text = "\n\n".join(
                f"- {item.get('title', '')}\n  {item.get('url', '')}\n  {item.get('snippet', '')}"
                for item in search_results
            )
        else:
            results_text = "(검색 결과 없음)"

        message = (
            f"제목:\n{task.title}\n\n"
            f"검색어:\n{query}\n\n"
            f"검색 결과:\n{results_text}"
        )
        self._show_scrollable_result_dialog("조사 완료", message)

    def _ensure_research_review_service(self) -> ResearchReviewService | None:
        """Reviewer(조사 결과 분석)도 research와 동일하게 실제로 쓸 때만 지연 생성한다.

        Brain/TaskSystem과 동일한 방식으로 OPENAI_API_KEY를 읽어 OpenAI
        client를 만들고, 그 client를 OpenAIResearchReviewerProvider에 그대로
        주입한다. Provider 내부에서는 API Key를 다시 읽지 않는다.
        """
        if self.research_review_service is not None:
            return self.research_review_service

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            QMessageBox.warning(
                self,
                "분석 실행 불가",
                "OpenAI API Key가 설정되지 않았습니다. "
                "프로젝트 루트의 .env 파일에 OPENAI_API_KEY 값을 입력한 뒤 다시 시도해주세요.",
            )
            return None

        client = OpenAI(api_key=api_key)
        provider = OpenAIResearchReviewerProvider(client)
        self.research_review_service = ResearchReviewService(provider, parent=self)
        self.research_review_service.result_ready.connect(self._on_research_review_result)
        self.research_review_service.error_occurred.connect(self._on_research_review_error)
        return self.research_review_service

    def _start_research_review(self, task: Task):
        """Research 검색이 성공한 뒤, 검색 결과를 Reviewer에게 넘겨 분석을 시작한다.

        Reviewer를 실행할 수 없는 상황(API Key 미설정 등)에서는 검색 결과
        자체는 이미 확보되어 있으므로, 기존처럼 검색 결과 팝업이라도
        보여준다 - 검색 결과를 잃지 않는다.
        """
        review_service = self._ensure_research_review_service()
        if review_service is None:
            self.work_step_value_label.setText("조사 완료")
            self._show_research_result_popup(task)
            return

        result = task.result or {}
        request = ResearchReviewRequest(
            task_title=task.title,
            task_goal=task.goal,
            query=result.get("query", ""),
            search_results=result.get("search_results", []),
        )

        self.work_step_value_label.setText("분석 중")
        review_service.review(request)

    def _on_research_review_result(self, result: ResearchReviewResult):
        self._current_research_review_result = result
        self.work_step_value_label.setText("분석 완료")
        self._show_research_review_popup(result)

    def _on_research_review_error(self, message: str):
        self.work_step_value_label.setText("분석 오류")
        QMessageBox.warning(self, "분석 실패", message)

    def _show_research_review_popup(self, result: ResearchReviewResult):
        task = self._current_task
        task_result = (task.result or {}) if task else {}
        query = task_result.get("query", "")
        search_result_count = len(task_result.get("search_results", []))

        observations = "\n".join(f"- {item}" for item in result.market_observations) or "(없음)"
        candidates = "\n".join(f"- {item}" for item in result.candidate_ideas) or "(없음)"
        risks = "\n".join(f"- {item}" for item in result.risks) or "(없음)"

        message = (
            f"조사 제목:\n{task.title if task else ''}\n\n"
            f"검색어:\n{query}\n\n"
            f"검색 결과 {search_result_count}건 분석\n\n"
            f"시장 관찰:\n{observations}\n\n"
            f"후보 아이디어:\n{candidates}\n\n"
            f"최종 추천:\n{result.recommended_idea}\n\n"
            f"추천 이유:\n{result.recommendation_reason}\n\n"
            f"리스크:\n{risks}\n\n"
            f"다음 행동:\n{result.next_action}"
        )
        self._show_scrollable_result_dialog("조사 분석 완료", message)

    def _ensure_orchestration_service(self) -> OrchestrationService | None:
        """복합 업무를 실제로 실행할 때만 OrchestrationService를 지연 생성한다.

        research는 TaskSystem(_ensure_task_system, research와 동일한 인스턴스를
        재사용 - API Key를 여러 곳에서 새로 읽지 않는다)으로, development는
        DevelopmentExecutor(OpenAIDeveloperProvider, 개발 실행 버튼과 동일한
        Provider 계약)로, analysis는 AnalysisExecutor(OpenAIResearchReviewerProvider,
        30단계 - 단일 Research Reviewer(_ensure_research_review_service)와
        완전히 동일한 client 생성 패턴을 재사용한다. 새 Analysis 전용 AI
        Provider는 만들지 않는다)로 실행한다. 이 시점에는 이미
        _ensure_task_system()이 API Key 존재를 확인/경고했으므로(위에서
        None이면 이미 return했다), 여기서 os.environ을 다시 읽을 때 별도
        경고 분기가 필요 없다.
        """
        if self.orchestration_service is not None:
            return self.orchestration_service

        task_system = self._ensure_task_system()
        if task_system is None:
            return None

        development_executor = DevelopmentExecutor(OpenAIDeveloperProvider())
        reviewer_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        analysis_executor = AnalysisExecutor(OpenAIResearchReviewerProvider(reviewer_client))
        orchestrator = ChiefBrainOrchestrator(
            task_system, development_executor=development_executor, analysis_executor=analysis_executor
        )

        self.orchestration_service = OrchestrationService(orchestrator, parent=self)
        self.orchestration_service.result_ready.connect(self._on_orchestration_result)
        self.orchestration_service.error_occurred.connect(self._on_orchestration_error)
        self.orchestration_service.stage_changed.connect(self._on_orchestration_stage_changed)
        return self.orchestration_service

    def _on_chief_plan_execute_button_clicked(self):
        if self._current_chief_plan is None:
            return

        orchestration_service = self._ensure_orchestration_service()
        if orchestration_service is None:
            return

        self.chief_plan_execute_button.setEnabled(False)
        self.work_step_value_label.setText("업무 실행 중")

        orchestration_service.run(self._current_chief_plan)

    def _on_orchestration_stage_changed(self, stage: str):
        self.work_step_value_label.setText(stage)
        self._apply_stage_to_ai_team(stage)

    def _apply_stage_to_ai_team(self, stage: str):
        """31단계 stage_changed 문자열("N/전체 task_type 시작"/"완료"/"승인
        대기")을 그대로 재사용해 AI TEAM 상태를 갱신한다. Orchestrator에
        새 이벤트 시스템을 만들지 않는다(3단계) - 여기서는 이미 오는
        문자열을 읽기만 한다.
        """
        if "research" in stage:
            if "시작" in stage:
                self.research_status_label.setText("조사 중")
            elif "완료" in stage:
                self.research_status_label.setText("완료")
        elif "analysis" in stage:
            if "시작" in stage:
                self.analysis_status_label.setText("분석 중")
            elif "완료" in stage:
                self.analysis_status_label.setText("완료")
        elif "development" in stage:
            if "시작" in stage:
                self.developer_status_label.setText("개발 중")
            elif "완료" in stage:
                self.developer_status_label.setText("완료")
        elif "screen_observation" in stage and "승인 대기" in stage:
            self.chief_brain_status_label.setText("승인 대기")

    def _mark_ai_team_error(self, task_type: str):
        if task_type == "research":
            self.research_status_label.setText("오류")
        elif task_type == "analysis":
            self.analysis_status_label.setText("오류")
        elif task_type == "development":
            self.developer_status_label.setText("오류")
        elif task_type == _SCREEN_OBSERVATION_TASK_TYPE:
            self.chief_brain_status_label.setText("오류")

    _ORCHESTRATION_STATUS_LABELS = {
        "completed": "업무 완료",
        "waiting_for_approval": "승인 대기",
        "waiting_for_review": "결과 검토 대기",
        "waiting_for_executor": "실행 대기",
        "failed": "업무 오류",
        "blocked": "업무 중단",
    }

    def _on_orchestration_result(self, result: OrchestrationResult):
        self.chief_plan_execute_button.setEnabled(True)
        self.work_step_value_label.setText(self._ORCHESTRATION_STATUS_LABELS.get(result.status, result.status))
        self._last_orchestration_result = result

        # 41단계 §11 - step 완료/승인 대기 진입/결과 검토 대기 진입/최종
        # 완료/resume 이후 상태 변화가 전부 이 한 곳으로 모인다(원래
        # project plan의 실행 결과는 항상 이 슬롯을 거친다) - 새 저장
        # 훅을 여러 곳에 흩어 놓지 않고 여기 하나만 연결한다.
        self._save_active_project_state()

        pending_step_result = result.completed_steps[-1] if result.completed_steps else None

        if result.status == "failed" and pending_step_result is not None:
            # 6단계 - 어느 단계에서 실패했는지 AI TEAM에 표시한다. 실패한
            # step의 내부 Exception 내용/Chain of Thought는 여기서 다루지
            # 않는다(work_step_value_label/결과 Dialog가 이미 요약된
            # 오류 메시지만 보여준다).
            self._mark_ai_team_error(pending_step_result.task_type)

        if (
            result.status == "waiting_for_approval"
            and pending_step_result is not None
            and pending_step_result.task_type == _SCREEN_OBSERVATION_TASK_TYPE
        ):
            # 일반 waiting_for_approval(예: 게시/발송처럼 다른 이유로
            # 승인이 필요한 단계)은 기존 결과 Dialog(승인 필요 안내만
            # 표시)를 그대로 쓴다 - screen_observation만 전용 승인 Dialog로
            # 처리한다(5단계).
            self._handle_screen_observation_approval(pending_step_result)
            return

        if (
            result.status == "waiting_for_approval"
            and pending_step_result is not None
            and self._current_chief_plan is not None
            and self._current_chief_plan.execution_mode == "project"
        ):
            # 34단계 - project 체크포인트. screen_observation은 바로 위
            # 분기에서 이미 return했으므로, 여기 도달하는
            # waiting_for_approval은 project 체크포인트(Chief Brain이
            # 직접 설정했거나 §3 안전장치가 강제로 만든 승인 대기)뿐이다.
            self._handle_project_checkpoint_approval(pending_step_result)
            return

        if result.status == "waiting_for_review" and pending_step_result is not None:
            # 36단계 - project development 결과 검토. "승인 대기"와는
            # 별개의 상태이므로 위의 waiting_for_approval 분기들과
            # 겹치지 않는다(개발은 이미 끝났다).
            self._handle_development_review(pending_step_result)
            return

        self._show_orchestration_result_dialog(result)

    def _on_orchestration_error(self, message: str):
        self.chief_plan_execute_button.setEnabled(True)
        self.work_step_value_label.setText("업무 오류")
        QMessageBox.warning(self, "업무 실행 실패", message)

    @staticmethod
    def _find_plan_step(plan: ChiefBrainPlan, step_id: str) -> BrainTaskStep | None:
        for step in plan.steps:
            if step.step_id == step_id:
                return step
        return None

    def _handle_screen_observation_approval(self, pending_step_result: OrchestrationStepResult):
        """screen_observation step이 waiting_for_approval로 멈췄을 때 호출된다.

        승인 Dialog를 보여주고, 사용자가 승인하면(15단계 개인정보 원칙:
        캡처 전 승인 필수, 승인 후 한 번만 캡처) 그 자리에서 화면을 캡처해
        분석을 요청한다. 취소하면 아무것도 캡처하지 않고 상태만 안내한다
        (14단계 - 완료된 앞 단계 결과는 그대로 보관되어 있다,
        self._last_orchestration_result 참고).
        """
        plan = self._current_chief_plan
        step = self._find_plan_step(plan, pending_step_result.step_id) if plan is not None else None
        if plan is None or step is None:
            # 방어적 처리 - 계획에 없는 step_id일 수 없지만, 혹시라도
            # 어긋나면 조용히 무시하지 않고 기존 결과 Dialog로 대체한다.
            self.work_step_value_label.setText("화면 확인 오류")
            self._show_orchestration_result_dialog(self._last_orchestration_result)
            return

        self.work_step_value_label.setText("화면 확인 승인 대기")
        approved = self._show_screen_observation_approval_dialog(step)
        if not approved:
            self.work_step_value_label.setText("화면 확인 취소됨")
            return

        self.work_step_value_label.setText("화면 확인 중")
        try:
            image = screen_capture.capture_primary_screen()
            png_bytes = _encode_image_to_png_bytes(image)
            image_content.validate_encoded_image_size(png_bytes)
        except (screen_capture.ScreenCaptureError, image_content.ImageAttachmentError) as exc:
            self.work_step_value_label.setText("화면 확인 실패")
            QMessageBox.warning(self, "화면 확인 실패", str(exc))
            return
        except Exception:
            # 알 수 없는 캡처/인코딩 실패도 앱 전체를 죽이지 않고 안전하게
            # 알린다. KeyboardInterrupt/SystemExit는 Exception이 아니므로
            # 여기서 잡히지 않고 그대로 전파된다.
            self.work_step_value_label.setText("화면 확인 실패")
            QMessageBox.warning(self, "화면 확인 실패", "현재 화면을 캡처하지 못했습니다.")
            return

        data_url = image_content.encode_png_bytes_to_data_url(png_bytes)

        screen_observation_service = self._ensure_screen_observation_service()
        self._pending_screen_observation_step = step
        screen_observation_service.observe(step, plan.objective, data_url)

    def _show_screen_observation_approval_dialog(self, step: BrainTaskStep) -> bool:
        """"화면 공유 승인"/"취소" 두 버튼만 있는 최소 승인 Dialog.

        기본값은 승인이 아니다(15단계) - "취소" 버튼을 기본/포커스 버튼으로
        둬서 Enter 키를 눌러도 승인되지 않는다.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("화면 확인 승인")

        layout = QVBoxLayout(dialog)
        message = QLabel(
            "Chief Brain이 현재 화면을 확인하려고 합니다.\n\n"
            f"목적:\n{step.goal}\n\n"
            f"이유:\n{step.approval_reason or ''}\n\n"
            "승인하면 현재 화면 이미지가 AI 분석을 위해 전송됩니다."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        button_row = QHBoxLayout()
        approve_button = QPushButton("화면 공유 승인")
        cancel_button = QPushButton("취소")
        button_row.addWidget(approve_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        approve_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        cancel_button.setDefault(True)
        cancel_button.setFocus()

        return dialog.exec() == QDialog.DialogCode.Accepted

    def _ensure_screen_observation_service(self) -> ScreenObservationService:
        if self.screen_observation_service is not None:
            return self.screen_observation_service

        executor = ScreenObservationExecutor(OpenAIScreenObservationProvider())
        self.screen_observation_service = ScreenObservationService(executor, parent=self)
        self.screen_observation_service.result_ready.connect(self._on_screen_observation_result)
        self.screen_observation_service.error_occurred.connect(self._on_screen_observation_error)
        return self.screen_observation_service

    def _on_screen_observation_result(self, observation_result: ScreenObservationResult):
        self.work_step_value_label.setText("화면 확인 완료")

        step = self._pending_screen_observation_step
        self._pending_screen_observation_step = None
        if step is None or self._last_orchestration_result is None or self._current_chief_plan is None:
            return

        approved_step_result = OrchestrationStepResult(
            step_id=step.step_id,
            task_type=step.task_type,
            status="completed",
            task_id=None,
            result=observation_result,
            error=None,
            requires_approval=step.requires_approval,
            approval_reason=step.approval_reason,
        )

        orchestration_service = self._ensure_orchestration_service()
        if orchestration_service is None:
            return

        self.work_step_value_label.setText("업무 실행 중")
        orchestration_service.resume(
            self._current_chief_plan, self._last_orchestration_result.completed_steps, approved_step_result
        )

    def _on_screen_observation_error(self, message: str):
        self.work_step_value_label.setText("화면 확인 오류")
        QMessageBox.warning(self, "화면 확인 실패", message)

    def _handle_project_checkpoint_approval(self, pending_step_result: OrchestrationStepResult):
        """34단계 - project 체크포인트에서 waiting_for_approval로 멈췄을 때 호출된다.

        screen_observation과 달리 승인은 "이 step을 지금부터 실제로
        실행해도 된다"는 뜻일 뿐이다(캡처처럼 UI에서 미리 해둘 일이
        없다) - 승인하면 바로 resume_project_checkpoint()를 호출해 그
        step을 처음 실행시킨다. 승인 이유는 pending_step_result의
        approval_reason을 쓴다(원본 BrainTaskStep.approval_reason이
        아니다) - §3 안전장치가 강제로 만든 승인 대기는 원본 step에
        approval_reason이 비어 있을 수 있고, 실제로 보여줘야 할 이유는
        OrchestrationStepResult 쪽에 담겨 있다(chief_brain_orchestrator.py
        참고).
        """
        plan = self._current_chief_plan
        step = self._find_plan_step(plan, pending_step_result.step_id) if plan is not None else None
        if plan is None or step is None:
            self.work_step_value_label.setText("업무 확인 오류")
            self._show_orchestration_result_dialog(self._last_orchestration_result)
            return

        self.work_step_value_label.setText("프로젝트 체크포인트 승인 대기")
        # 42단계 §4/§11 - 지금까지 완료된 research/analysis 결과를 함께
        # 보여준다. self._last_orchestration_result.completed_steps는
        # 원래 project 흐름이든(round34) 저장된 프로젝트를 불러온
        # 뒤든(round41 _resume_loaded_project) 이 시점에 항상 채워져
        # 있다 - 새 resume 시스템을 만들 필요가 없다.
        completed_steps = (
            self._last_orchestration_result.completed_steps if self._last_orchestration_result is not None else None
        )
        approved = self._show_project_checkpoint_approval_dialog(
            step, pending_step_result.approval_reason, completed_steps
        )
        if not approved:
            self.work_step_value_label.setText("프로젝트 체크포인트 대기 중")
            return

        orchestration_service = self._ensure_orchestration_service()
        if orchestration_service is None or self._last_orchestration_result is None:
            return

        self.work_step_value_label.setText("업무 실행 중")
        orchestration_service.resume_project_checkpoint(
            plan, self._last_orchestration_result.completed_steps, step.step_id
        )

    def _show_project_checkpoint_approval_dialog(
        self,
        step: BrainTaskStep,
        approval_reason: str | None,
        completed_steps: list[OrchestrationStepResult] | None = None,
    ) -> bool:
        """"진행 승인"/"프로젝트 저장"/"취소" 세 버튼이 있는 승인
        Dialog(4단계, 42단계에서 저장 버튼 + 이전 작업 결과 표시 추가).

        _show_screen_observation_approval_dialog와 동일한 패턴을 그대로
        따른다(새 Dialog 시스템을 만들지 않는다) - 기본값은 승인이
        아니다("취소"가 기본/포커스 버튼이다).

        42단계 §4/§5/§6 - completed_steps가 주어지면(원래 project
        checkpoint 흐름) 가장 최근 research/analysis 결과만 규칙 기반으로
        요약해 함께 보여준다(전체 기록 아님, 새 AI 요약 호출 없음).
        주어지지 않으면(기본값 None - 38단계 revision development
        checkpoint가 이 Dialog를 호출할 때는 여전히 넘기지 않는다) 이전
        기존 화면 그대로다 - revision loop 호출부는 전혀 바뀌지 않는다.

        §7/§8 - "프로젝트 저장" 버튼은 dialog.accept()/reject()를 호출하지
        않는다 - Qt에서는 그 둘을 부르기 전까지 모달 Dialog가 닫히지
        않으므로, 저장 핸들러가 그냥 반환하면 이 Dialog는 그대로 열려
        있는 채로 유지된다(별도의 "닫았다가 다시 연다" 구조가 필요
        없다). development는 오직 approve_button(dialog.accept)을 거쳐야만
        시작될 수 있다.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("프로젝트 체크포인트 승인")

        layout = QVBoxLayout(dialog)

        if completed_steps is not None:
            research_entry = find_latest_step_result(completed_steps, "research")
            analysis_entry = find_latest_step_result(completed_steps, "analysis")
            research_text = describe_step_result(research_entry) if research_entry is not None else "조사 결과 없음"
            analysis_text = describe_step_result(analysis_entry) if analysis_entry is not None else "분석 결과 없음"

            layout.addWidget(QLabel("--- 지금까지 완료된 작업 ---"))
            context_view = QPlainTextEdit()
            context_view.setReadOnly(True)
            context_view.setPlainText(f"[조사 결과]\n{research_text}\n\n[분석 결과]\n{analysis_text}")
            context_view.setMaximumHeight(220)
            layout.addWidget(context_view)
            layout.addWidget(QLabel("--- 다음 개발 단계 ---"))

        message = QLabel(
            "다음 개발 단계로 진행하기 전 확인이 필요합니다.\n\n"
            f"다음 단계:\n{step.title}\n\n"
            f"목표:\n{step.goal}\n\n"
            f"승인 이유:\n{approval_reason or ''}"
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        button_row = QHBoxLayout()
        approve_button = QPushButton("진행 승인")
        save_button = QPushButton("프로젝트 저장")
        cancel_button = QPushButton("취소")
        button_row.addWidget(approve_button)
        button_row.addWidget(save_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        approve_button.clicked.connect(dialog.accept)
        save_button.clicked.connect(self._on_checkpoint_save_button_clicked)
        cancel_button.clicked.connect(dialog.reject)
        cancel_button.setDefault(True)
        cancel_button.setFocus()

        return dialog.exec() == QDialog.DialogCode.Accepted

    def _on_checkpoint_save_button_clicked(self):
        """42단계 §7/§8/§9 - 승인 Dialog 안에서 누르는 저장 버튼.

        승인/취소로 처리하지 않는다(dialog.accept()/reject()를 호출하지
        않는다) - development를 시작하지 않고(resume_project_checkpoint를
        부르지 않는다), Orchestrator를 다시 실행하지 않으며, 현재
        waiting_for_approval 상태를 그대로 유지한다. 41단계의
        _save_active_project_state()를 그대로 재사용한다(새 저장
        시스템을 만들지 않는다) - 실패해도 project를 실패 처리하지
        않고 내부 예외 traceback 없이 안내만 한다(§9).
        """
        if self._save_active_project_state():
            QMessageBox.information(
                self,
                "프로젝트 저장",
                "현재 프로젝트 상태를 저장했습니다.\n승인 대기 상태는 그대로 유지됩니다.",
            )
        else:
            QMessageBox.warning(self, "프로젝트 저장 실패", "프로젝트 상태를 저장하지 못했습니다.")

    def _handle_development_review(self, pending_step_result: OrchestrationStepResult):
        """36단계 - project development step이 성공적으로 끝나면 다음
        step으로 자동 진행하지 않고 먼저 결과를 보여준다.

        "승인 대기"(project 체크포인트, 개발 시작 전)와는 다른 상태다 -
        여기서는 개발이 이미 끝났고(pending_step_result.status는
        "completed"), 그 결과를 사람이 보고 다음으로 갈지 결정한다.
        37단계 - "실행해서 확인"을 고르면 실제로 실행/캡처/분석한 뒤
        같은 결정 화면을 다시 보여준다(_present_development_review).
        """
        plan = self._current_chief_plan
        step = self._find_plan_step(plan, pending_step_result.step_id) if plan is not None else None
        dev_result = pending_step_result.result
        if plan is None or step is None or dev_result is None:
            self.work_step_value_label.setText("결과 확인 오류")
            self._show_orchestration_result_dialog(self._last_orchestration_result)
            return

        self.work_step_value_label.setText("프로젝트 결과 검토 대기")
        self.developer_status_label.setText("결과 검토 대기")

        # 39/40단계 §10/§4 - 이 step은 revision이 아니라 원래 계획의
        # development 단계가 방금 끝난 것이므로, 이전에 다른 step에서
        # 만들어진 수정 요약/전후 화면이 섞여 보이지 않도록 비운다.
        self._revision_last_summary = None
        self._revision_before_image = None
        self._revision_before_observation = None
        self._revision_after_image = None
        self._revision_after_observation = None

        self._present_development_review(step, dev_result, plan)

    def _present_development_review(
        self,
        step: BrainTaskStep,
        dev_result: DeveloperResult,
        plan: ChiefBrainPlan,
        execution_result: ExecutionResult | None = None,
        image_pixmap: QPixmap | None = None,
        observation_result: ScreenObservationResult | None = None,
    ):
        """37단계 - 결정 Dialog를 보여주고 "계속 진행"/"수정 요청"/
        "실행해서 확인" 중 선택에 따라 분기한다. 실행 검토 정보
        (execution_result/image_pixmap/observation_result)가 아직 없으면
        36단계와 동일한 텍스트 요약만 보여주고, 있으면 함께 보여준다 -
        "실행해서 확인" 이후에는 이 메서드가 그 결과를 들고 다시
        불린다.

        40단계 - revision 결과를 검토 중일 때(self._revision_last_summary가
        있을 때) 새로 받은 image_pixmap/observation_result는 "이번
        revision의 after 화면"으로 승격한다. 여기서만 승격하므로
        "실행해서 확인"을 다시 눌러 새 화면을 받을 때마다 after가
        최신으로 갱신된다 - revision이 아닌 일반 검토(revision_last_
        summary가 None)에서는 손대지 않는다(§4 - revision 단위 격리).
        """
        if self._revision_last_summary is not None and (image_pixmap is not None or observation_result is not None):
            self._revision_after_image = image_pixmap
            self._revision_after_observation = observation_result

        next_step = min((s for s in plan.steps if s.order > step.order), key=lambda s: s.order, default=None)
        decision = self._show_development_review_dialog(
            step,
            dev_result,
            next_step,
            execution_result,
            image_pixmap,
            observation_result,
            self._revision_last_summary,
            self._revision_before_image,
            self._revision_before_observation,
            self._revision_after_image,
            self._revision_after_observation,
        )

        if decision == "run":
            self._start_runtime_review(step, dev_result, plan)
            return

        if decision == "revise":
            # 38단계 - 36단계의 "안내만 하고 멈춘다"를 실제 수정 루프로
            # 대체한다(개발 -> 결과 확인 -> 수정 요청 -> 재개발 -> 다시
            # 결과 확인). 40단계 - 지금 보고 있는 image_pixmap도 함께
            # 넘긴다(다음 revision의 before로 승격시키기 위해, §11).
            self._start_development_revision(step, dev_result, plan, observation_result, image_pixmap)
            return

        orchestration_service = self._ensure_orchestration_service()
        if orchestration_service is None or self._last_orchestration_result is None:
            return

        self.work_step_value_label.setText("업무 실행 중")
        orchestration_service.resume_after_review(plan, self._last_orchestration_result.completed_steps)

    def _show_development_review_dialog(
        self,
        step: BrainTaskStep,
        dev_result: DeveloperResult,
        next_step: BrainTaskStep | None,
        execution_result: ExecutionResult | None = None,
        image_pixmap: QPixmap | None = None,
        observation_result: ScreenObservationResult | None = None,
        revision_summary: DevelopmentRevisionSummary | None = None,
        before_image: QPixmap | None = None,
        before_observation: ScreenObservationResult | None = None,
        after_image: QPixmap | None = None,
        after_observation: ScreenObservationResult | None = None,
    ) -> str:
        """"계속 진행"/"실행해서 확인"/"수정 요청" 세 버튼이 있는 결과
        검토 Dialog(§2/§5/§11). 반환값은 "continue"/"run"/"revise" 중
        하나다.

        기존 승인 Dialog들과 동일한 패턴을 그대로 따른다(새 Dialog
        시스템이 아니다). 표시 정보는 DeveloperResult/ExecutionResult/
        ScreenObservationResult의 실제 필드에서만 가져온다(없는 정보를
        지어내지 않는다). "실행해서 확인"은 project_path/entry_point가
        둘 다 있을 때만 활성화한다(§4). 기본값은 자동 진행이 아니다 -
        "수정 요청"이 기본/포커스 버튼이라 Enter로는 다음 단계로
        넘어가지 않는다.

        40단계 - before_image/after_image는 revision 전/후 실행 화면
        비교 전용이다(revision_summary가 있을 때만 의미가 있다). AI
        비교 판단을 새로 만들지 않는다(§7) - 기존 ScreenObservationResult
        각각을 그대로 나란히 보여줄 뿐이다(§8).
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("개발 단계 결과 확인")

        created_text = "\n".join(f"   - {name}" for name in dev_result.created_files) or "   없음"
        modified_text = "\n".join(f"   - {name}" for name in dev_result.modified_files) or "   없음"
        error_text = "; ".join(dev_result.errors) if dev_result.errors else "없음"
        next_text = next_step.title if next_step is not None else "없음(마지막 단계)"

        message_text = (
            f"이번 단계:\n{step.title}\n\n"
            f"완료 내용:\n{dev_result.summary}\n\n"
            f"생성된 파일:\n{created_text}\n\n"
            f"수정된 파일:\n{modified_text}\n\n"
            f"오류 여부:\n{error_text}\n\n"
            f"다음 단계:\n{next_text}"
        )

        if revision_summary is not None:
            # 39단계 §6 - 사용자가 코드를 몰라도 이해할 수 있도록 "무엇이
            # 바뀌었는지"를 먼저 보여준다. 화면 검증 전이므로 "요청이
            # 반영됐다"는 확정 표현은 쓰지 않는다(§8, revision_summary.
            # summary 문구 자체가 이미 그 원칙을 따른다).
            changed_text = "\n".join(f"   - {name}" for name in revision_summary.changed_files) or "   없음"
            added_text = "\n".join(f"   - {name}" for name in revision_summary.added_files) or "   없음"
            removed_text = "\n".join(f"   - {name}" for name in revision_summary.removed_files) or "   없음"
            warnings_text = "\n".join(f"   - {item}" for item in revision_summary.warnings) or "   없음"
            message_text += (
                f"\n\n--- 수정 내역 ---\n"
                f"수정 요청:\n{revision_summary.requested_change}\n\n"
                f"수정된 파일:\n{changed_text}\n\n"
                f"추가된 파일:\n{added_text}\n\n"
                f"삭제된 파일:\n{removed_text}\n\n"
                f"변경 요약:\n{revision_summary.summary}\n\n"
                f"주의사항:\n{warnings_text}"
            )

            # 40단계 §5/§6/§8/§9 - revision 전/후 화면 비교. before가
            # 아예 없으면(사용자가 revision 전에 "실행해서 확인"을 한
            # 적이 없으면) 비교 자체를 제공하지 않고 그 사실만 안내한다
            # - revision을 막지는 않는다(39단계 텍스트 요약은 위에서
            # 이미 정상 표시됐다).
            if before_image is None:
                message_text += "\n\n수정 전 실행 화면이 없어 화면 비교는 제공할 수 없습니다."
            else:
                before_obs_text = before_observation.summary if before_observation is not None else "화면 분석 결과 없음"
                if after_image is None:
                    after_obs_text = "아직 확인하지 않음"
                elif after_observation is not None:
                    after_obs_text = after_observation.summary
                else:
                    after_obs_text = "화면 분석 결과 없음"
                message_text += (
                    f"\n\n--- 화면 비교(수정 전/후) ---\n"
                    f"수정 전 화면 분석:\n{before_obs_text}\n\n"
                    f"수정 후 화면 분석:\n{after_obs_text}"
                )

        if execution_result is not None:
            exec_status_text = "성공" if execution_result.status == "success" else "실패"
            message_text += f"\n\n--- 실행 결과 ---\n실행 성공 여부: {exec_status_text}\n{execution_result.summary}"
            if image_pixmap is None and observation_result is None:
                message_text += "\n(화면 확인 불가 - 실행 결과만 표시합니다.)"

        if observation_result is not None:
            observations_text = "\n".join(f"   - {item}" for item in observation_result.observations) or "   없음"
            issues_text = "\n".join(f"   - {item}" for item in observation_result.issues) or "   없음"
            message_text += (
                f"\n\n--- 화면 분석 ---\n"
                f"Brain 화면 분석 요약:\n{observation_result.summary}\n\n"
                f"관찰된 기능:\n{observations_text}\n\n"
                f"문제점:\n{issues_text}\n\n"
                f"다음 행동:\n{observation_result.next_action}"
            )

        layout = QVBoxLayout(dialog)
        message = QLabel(message_text)
        message.setWordWrap(True)
        layout.addWidget(message)

        if image_pixmap is not None:
            # §11 - 사용자가 실제 실행 화면을 직접 볼 수 있어야 한다
            # (Brain 텍스트 분석만으로 끝내지 않는다).
            image_label = QLabel()
            image_label.setPixmap(image_pixmap)
            layout.addWidget(image_label)

        if revision_summary is not None and before_image is not None:
            # 40단계 §6 - 대규모 이미지 뷰어가 아니라 QLabel + 이미
            # scaled된 QPixmap(37단계에서 이미 480x360으로 scale됨)을
            # 나란히 두는 최소 UI다.
            image_row = QHBoxLayout()

            before_column = QVBoxLayout()
            before_column.addWidget(QLabel("수정 전"))
            before_image_label = QLabel()
            before_image_label.setPixmap(before_image)
            before_column.addWidget(before_image_label)
            image_row.addLayout(before_column)

            after_column = QVBoxLayout()
            after_column.addWidget(QLabel("수정 후"))
            if after_image is not None:
                after_image_label = QLabel()
                after_image_label.setPixmap(after_image)
                after_column.addWidget(after_image_label)
            else:
                after_column.addWidget(QLabel("아직 확인하지 않음"))
            image_row.addLayout(after_column)

            layout.addLayout(image_row)

        button_row = QHBoxLayout()
        continue_button = QPushButton("계속 진행")
        run_button = QPushButton("실행해서 확인")
        revise_button = QPushButton("수정 요청")
        button_row.addWidget(continue_button)
        button_row.addWidget(run_button)
        button_row.addWidget(revise_button)
        layout.addLayout(button_row)

        can_run = bool(dev_result.project_path) and bool(dev_result.entry_point)
        run_button.setEnabled(can_run)
        if not can_run:
            run_button.setToolTip("실행 파일 정보(project_path/entry_point)가 없어 실행할 수 없습니다.")

        continue_button.clicked.connect(lambda: dialog.done(1))
        run_button.clicked.connect(lambda: dialog.done(2))
        revise_button.clicked.connect(lambda: dialog.done(0))
        revise_button.setDefault(True)
        revise_button.setFocus()

        exec_result_code = dialog.exec()
        return {1: "continue", 2: "run", 0: "revise"}.get(exec_result_code, "revise")

    # 37단계 §7 - 프로그램이 실행된 뒤 화면이 그려질 시간을 벌기 위한
    # 짧은 추가 지연이다. run_entry_point(project_runner.py)가 이미
    # LIVENESS_CHECK_SECONDS(3초)만큼 프로세스 생존을 기다린 뒤에야
    # result_ready가 오므로(그동안 이미 창이 뜰 시간을 번다), 여기서는
    # 화면 렌더링 마무리를 위한 짧은 여유만 QTimer.singleShot으로
    # UI thread를 막지 않고 둔다. 대규모 프로세스 모니터링을 새로 만들지
    # 않는다.
    _RUNTIME_REVIEW_CAPTURE_DELAY_MS = 700

    def _start_runtime_review(self, step: BrainTaskStep, dev_result: DeveloperResult, plan: ChiefBrainPlan):
        """37단계 §2/§3/§5 - 사용자가 "실행해서 확인"을 명시적으로
        눌렀을 때만 호출된다(자동/반복/백그라운드 실행 없음). 기존
        ExecutionService 계약(project_path/entry_point 검증 ->
        run_project)을 그대로 재사용하되, 단일 development "프로그램
        실행" 버튼(execute_button/execution_service)과는 완전히 분리된
        인스턴스로 실행한다.
        """
        try:
            entry_point = resolve_entry_point(Path(dev_result.project_path), dev_result.entry_point)
        except EntryPointError:
            QMessageBox.warning(self, "실행 불가", "프로그램 실행 파일을 확인할 수 없습니다.")
            self._present_development_review(step, dev_result, plan)
            return

        self._runtime_review_step = step
        self._runtime_review_dev_result = dev_result
        self._runtime_review_plan = plan
        self._runtime_review_execution_result = None
        self._runtime_review_image_pixmap = None

        self.work_step_value_label.setText("개발 결과 실행 중")
        self.developer_status_label.setText("프로그램 실행 중")

        review_execution_service = self._ensure_review_execution_service()
        # v1은 requirements 설치 확인 UI까지는 만들지 않는다(§18 최소
        # 변경) - 기존 venv가 있으면 그대로 재사용되고, 표준 라이브러리만
        # 쓰는 프로그램은 정상 실행된다. 패키지가 더 필요한데 설치돼
        # 있지 않으면 실행 실패로 안전하게 처리된다(§14).
        review_execution_service.run_project(Path(dev_result.project_path), entry_point, False)

    def _ensure_review_execution_service(self) -> ExecutionService:
        if self.review_execution_service is not None:
            return self.review_execution_service

        self.review_execution_service = ExecutionService(parent=self)
        self.review_execution_service.result_ready.connect(self._on_review_execution_result)
        self.review_execution_service.error_occurred.connect(self._on_review_execution_error)
        self.review_execution_service.stage_changed.connect(self._on_review_execution_stage_changed)
        return self.review_execution_service

    def _on_review_execution_stage_changed(self, stage: str):
        self.work_step_value_label.setText(stage)

    def _on_review_execution_result(self, result: ExecutionResult):
        step = self._runtime_review_step
        dev_result = self._runtime_review_dev_result
        plan = self._runtime_review_plan
        if step is None or dev_result is None or plan is None:
            return

        if result.status != "success":
            # §14 - 실행 실패해도 project 전체를 failed 처리하지 않는다.
            # waiting_for_review를 유지한 채 실행 결과만 보여준다.
            self.work_step_value_label.setText("프로젝트 결과 검토 대기")
            self.developer_status_label.setText("결과 검토 대기")
            self._present_development_review(step, dev_result, plan, execution_result=result)
            return

        self._runtime_review_execution_result = result
        self.work_step_value_label.setText("화면 확인 중")
        self.developer_status_label.setText("화면 확인 중")
        QTimer.singleShot(self._RUNTIME_REVIEW_CAPTURE_DELAY_MS, self._capture_runtime_review_screen)

    def _on_review_execution_error(self, message: str):
        step = self._runtime_review_step
        dev_result = self._runtime_review_dev_result
        plan = self._runtime_review_plan
        self.work_step_value_label.setText("프로젝트 결과 검토 대기")
        self.developer_status_label.setText("결과 검토 대기")
        QMessageBox.warning(self, "실행 확인 실패", message)
        if step is not None and dev_result is not None and plan is not None:
            self._present_development_review(step, dev_result, plan)

    def _capture_runtime_review_screen(self):
        """37단계 §6 - 기존 screen_capture.py + image_content 파이프라인을
        그대로 재사용한다(round 29 _handle_screen_observation_approval과
        동일한 캡처/인코딩 경로) - 디스크에 임시 파일을 저장하지 않는다.
        """
        step = self._runtime_review_step
        dev_result = self._runtime_review_dev_result
        plan = self._runtime_review_plan
        execution_result = self._runtime_review_execution_result
        if step is None or dev_result is None or plan is None:
            return

        try:
            image = screen_capture.capture_primary_screen()
            png_bytes = _encode_image_to_png_bytes(image)
            image_content.validate_encoded_image_size(png_bytes)
        except (screen_capture.ScreenCaptureError, image_content.ImageAttachmentError) as exc:
            self.work_step_value_label.setText("프로젝트 결과 검토 대기")
            self.developer_status_label.setText("결과 검토 대기")
            QMessageBox.warning(self, "화면 확인 실패", str(exc))
            self._present_development_review(step, dev_result, plan, execution_result=execution_result)
            return
        except Exception:
            # 알 수 없는 캡처/인코딩 실패도 §14에 따라 project를 죽이지
            # 않고 안전하게 알린다. KeyboardInterrupt/SystemExit는
            # Exception이 아니므로 여기서 잡히지 않고 그대로 전파된다.
            self.work_step_value_label.setText("프로젝트 결과 검토 대기")
            self.developer_status_label.setText("결과 검토 대기")
            QMessageBox.warning(self, "화면 확인 실패", "현재 화면을 캡처하지 못했습니다.")
            self._present_development_review(step, dev_result, plan, execution_result=execution_result)
            return

        self._runtime_review_image_pixmap = QPixmap.fromImage(image).scaled(
            480, 360, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        data_url = image_content.encode_png_bytes_to_data_url(png_bytes)

        self.work_step_value_label.setText("결과 화면 분석 중")
        self.developer_status_label.setText("화면 확인 중")

        # 37단계 §8/§9 - 새 Vision AI Provider/Request/Result 모델을
        # 만들지 않는다. 기존 ScreenObservationExecutor.execute()가 받는
        # BrainTaskStep 하나만 이 검토 전용으로 즉석에서 구성한다(plan에
        # 추가되지 않는 임시 객체) - development_executor.py가 선행 step
        # 결과를 "goal 뒤에 참고자료로만" 덧붙이는 것과 동일한 방식으로,
        # step.title/goal/dev_result.summary를 goal 하나에 모은다.
        review_step = BrainTaskStep(
            step_id=step.step_id,
            order=step.order,
            task_type=_SCREEN_OBSERVATION_TASK_TYPE,
            title=step.title,
            goal=f"{step.title}\n\n{step.goal}\n\n개발 결과 요약:\n{dev_result.summary}",
            depends_on=[],
            requires_approval=True,
            approval_reason="development 결과가 실제로 실행된 화면을 검토하기 위한 캡처입니다.",
        )
        review_screen_observation_service = self._ensure_review_screen_observation_service()
        review_screen_observation_service.observe(review_step, plan.objective, data_url)

    def _ensure_review_screen_observation_service(self) -> ScreenObservationService:
        if self.review_screen_observation_service is not None:
            return self.review_screen_observation_service

        executor = ScreenObservationExecutor(OpenAIScreenObservationProvider())
        self.review_screen_observation_service = ScreenObservationService(executor, parent=self)
        self.review_screen_observation_service.result_ready.connect(self._on_review_screen_observation_result)
        self.review_screen_observation_service.error_occurred.connect(self._on_review_screen_observation_error)
        return self.review_screen_observation_service

    def _on_review_screen_observation_result(self, observation_result: ScreenObservationResult):
        step = self._runtime_review_step
        dev_result = self._runtime_review_dev_result
        plan = self._runtime_review_plan
        execution_result = self._runtime_review_execution_result
        image_pixmap = self._runtime_review_image_pixmap
        self.work_step_value_label.setText("프로젝트 결과 검토 대기")
        self.developer_status_label.setText("결과 검토 대기")
        if step is None or dev_result is None or plan is None:
            return
        self._present_development_review(
            step,
            dev_result,
            plan,
            execution_result=execution_result,
            image_pixmap=image_pixmap,
            observation_result=observation_result,
        )

    def _on_review_screen_observation_error(self, message: str):
        step = self._runtime_review_step
        dev_result = self._runtime_review_dev_result
        plan = self._runtime_review_plan
        execution_result = self._runtime_review_execution_result
        image_pixmap = self._runtime_review_image_pixmap
        self.work_step_value_label.setText("프로젝트 결과 검토 대기")
        self.developer_status_label.setText("결과 검토 대기")
        QMessageBox.warning(self, "화면 분석 실패", message)
        if step is not None and dev_result is not None and plan is not None:
            self._present_development_review(
                step, dev_result, plan, execution_result=execution_result, image_pixmap=image_pixmap
            )

    def _start_development_revision(
        self,
        step: BrainTaskStep,
        dev_result: DeveloperResult,
        plan: ChiefBrainPlan,
        observation_result: ScreenObservationResult | None,
        image_pixmap: QPixmap | None = None,
    ):
        """38단계 §4 - "수정 요청"을 실제로 입력받는다.

        빈 문자열/취소는 전송하지 않는다(waiting_for_review 그대로
        유지, 아무 것도 호출하지 않는다). 37단계 screen 검토를 거쳤다면
        observation_result가 있고, 없으면 None을 그대로 Request에
        넘긴다(§14 - 없는 화면 분석을 지어내지 않는다).

        40단계 §4/§11 - 지금 사용자가 보고 있던 image_pixmap/
        observation_result를 이번 revision의 "before" 화면으로
        승격한다(반복 수정 시 직전 after가 다음 before가 되는 것과
        동일한 원리). after는 아직 없으므로 비운다 - 다음
        "실행해서 확인"에서 새로 채워진다(_present_development_review).
        """
        text, ok = QInputDialog.getMultiLineText(self, "수정 요청", "수정 요청 내용을 입력하세요:", "")
        if not ok or not text.strip():
            return

        self._revision_original_step = step
        self._revision_original_dev_result = dev_result
        self._revision_original_plan = plan
        self._revision_user_request_text = text.strip()
        self._revision_before_image = image_pixmap
        self._revision_before_observation = observation_result
        self._revision_after_image = None
        self._revision_after_observation = None
        # 39단계 §4 - revision 시작 "전" 파일 목록을 메모리에만 보관한다
        # (파일 내용 복사/디스크 snapshot 없음, 파일명만). 실패해도
        # None으로 안전하게 넘어간다(§12) - build_revision_summary가
        # None을 보고 "비교 실패"로 정직하게 표시한다.
        self._revision_before_files = self._safe_list_project_files(dev_result.project_path)

        request = DevelopmentRevisionRequest(
            project_objective=plan.objective,
            current_step_title=step.title,
            current_step_goal=step.goal,
            developer_summary=dev_result.summary,
            created_files=list(dev_result.created_files),
            modified_files=list(dev_result.modified_files),
            user_revision_request=self._revision_user_request_text,
            screen_observation_summary=observation_result.summary if observation_result is not None else None,
        )

        self.work_step_value_label.setText("수정 요청 분석 중")
        self.chief_brain_status_label.setText("수정 계획 중")
        self.developer_status_label.setText("수정 대기")

        revision_service = self._ensure_development_revision_service()
        revision_service.plan_revision(request)

    @staticmethod
    def _safe_list_project_files(project_path: str) -> list[str] | None:
        """39단계 §3/§4/§12 - WorkspaceGuard.list_files()를 그대로
        재사용해 파일명 기준으로만 비교한다(git 의존성 없음, 전체 내용
        복사/디스크 snapshot 없음). 실패해도 예외를 전파하지 않고 None을
        돌려줘 호출자가 "비교 실패"로 안전하게 처리할 수 있게 한다.
        """
        try:
            return WorkspaceGuard(Path(project_path)).list_files()
        except Exception:
            return None

    def _ensure_development_revision_service(self) -> DevelopmentRevisionService:
        if self.development_revision_service is not None:
            return self.development_revision_service

        executor = DevelopmentRevisionExecutor(OpenAIDevelopmentRevisionProvider())
        self.development_revision_service = DevelopmentRevisionService(executor, parent=self)
        self.development_revision_service.result_ready.connect(self._on_development_revision_plan_ready)
        self.development_revision_service.error_occurred.connect(self._on_development_revision_plan_error)
        return self.development_revision_service

    def _on_development_revision_plan_ready(self, revision_plan: DevelopmentRevisionPlan):
        """38단계 §6/§15 - Brain이 수정 판단을 마쳤다고 곧바로 Developer를
        실행하지 않는다. steps가 비어 있으면(코드 수정이 필요 없다는
        판단) 그 사실만 알리고 원래 review 상태로 돌아간다(§17). steps가
        있으면 승인 Dialog를 먼저 보여준다.
        """
        step = self._revision_original_step
        dev_result = self._revision_original_dev_result
        plan = self._revision_original_plan
        if step is None or dev_result is None or plan is None:
            return

        self.chief_brain_status_label.setText("대기")

        if not revision_plan.steps:
            self.developer_status_label.setText("결과 검토 대기")
            self.work_step_value_label.setText("프로젝트 결과 검토 대기")
            QMessageBox.information(self, "수정 계획", revision_plan.judgment)
            self._present_development_review(step, dev_result, plan)
            return

        self.work_step_value_label.setText("수정 계획 승인 대기")
        approved = self._show_development_revision_plan_dialog(revision_plan)
        if not approved:
            self.developer_status_label.setText("결과 검토 대기")
            self.work_step_value_label.setText("프로젝트 결과 검토 대기")
            self._present_development_review(step, dev_result, plan)
            return

        # 38단계 §7 - 이 임시 계획은 원래 project plan(plan.steps)을 전혀
        # 건드리지 않는다. chief_brain_plan.py의 계획 검증 함수도 거치지
        # 않는다(그 함수는 LLM이 만드는 project 전체 계획을 검증하기
        # 위한 것이지, 여기서 코드로 신중하게 구성한 부분 수정 계획에는
        # 적용되지 않는다) - execution_mode="project"로 두는 이유는 기존
        # round34 checkpoint 안전장치/round36 waiting_for_review를
        # 그대로 재사용하기 위해서일 뿐이다.
        self._revision_plan = ChiefBrainPlan(
            needs_more_info=False,
            ready=True,
            objective=plan.objective,
            execution_mode="project",
            steps=revision_plan.steps,
            clarification_question=None,
            user_reply=revision_plan.judgment,
        )

        self.work_step_value_label.setText("수정 작업 중")
        self.developer_status_label.setText("수정 중")

        revision_orchestration_service = self._ensure_revision_orchestration_service(dev_result.project_path)
        if revision_orchestration_service is None:
            return
        revision_orchestration_service.run(self._revision_plan)

    def _on_development_revision_plan_error(self, message: str):
        step = self._revision_original_step
        dev_result = self._revision_original_dev_result
        plan = self._revision_original_plan
        self.chief_brain_status_label.setText("오류")
        QMessageBox.warning(self, "수정 계획 실패", message)
        self.developer_status_label.setText("결과 검토 대기")
        self.work_step_value_label.setText("프로젝트 결과 검토 대기")
        if step is not None and dev_result is not None and plan is not None:
            self._present_development_review(step, dev_result, plan)

    def _show_development_revision_plan_dialog(self, revision_plan: DevelopmentRevisionPlan) -> bool:
        """"수정 시작 승인"/"취소" 두 버튼만 있는 최소 승인 Dialog(§15).

        기존 승인 Dialog들과 동일한 패턴을 그대로 따른다(새 승인
        시스템이 아니다) - 기본값은 승인이 아니다.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("수정 계획 확인")

        steps_text = (
            "\n".join(f"   {i}. [{s.task_type}] {s.title}" for i, s in enumerate(revision_plan.steps, start=1))
            or "   없음"
        )

        layout = QVBoxLayout(dialog)
        message = QLabel(
            f"Brain 판단:\n{revision_plan.judgment}\n\n"
            f"수정 작업:\n{steps_text}\n\n"
            f"영향 범위:\n{revision_plan.impact_summary}"
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        button_row = QHBoxLayout()
        approve_button = QPushButton("수정 시작 승인")
        cancel_button = QPushButton("취소")
        button_row.addWidget(approve_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        approve_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        cancel_button.setDefault(True)
        cancel_button.setFocus()

        return dialog.exec() == QDialog.DialogCode.Accepted

    def _ensure_revision_orchestration_service(self, existing_project_path: str) -> OrchestrationService | None:
        """38단계 - 기존 _ensure_orchestration_service()와 동일한 구성
        패턴을 그대로 따르되(§10 - 기존 DevelopmentExecutor/DeveloperRequest
        계약 재사용), DevelopmentExecutor에 existing_project_path를 줘서
        "새 프로젝트 생성"이 아니라 "기존 프로젝트 수정"이 되도록 한다.
        원래 project plan 실행에 쓰는 orchestration_service와는 완전히
        분리된 인스턴스다(§16 - 원래 흐름 무영향).
        """
        task_system = self._ensure_task_system()
        if task_system is None:
            return None

        development_executor = DevelopmentExecutor(
            OpenAIDeveloperProvider(), existing_project_path=existing_project_path
        )
        reviewer_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        analysis_executor = AnalysisExecutor(OpenAIResearchReviewerProvider(reviewer_client))
        orchestrator = ChiefBrainOrchestrator(
            task_system, development_executor=development_executor, analysis_executor=analysis_executor
        )

        self.revision_orchestration_service = OrchestrationService(orchestrator, parent=self)
        self.revision_orchestration_service.result_ready.connect(self._on_revision_orchestration_result)
        self.revision_orchestration_service.error_occurred.connect(self._on_revision_orchestration_error)
        # stage_changed는 순수하게 stage 문자열만으로 동작하는 기존
        # 슬롯을 그대로 재사용한다(self._current_chief_plan/
        # self._last_orchestration_result를 참조하지 않는다) - WORK
        # STATUS/AI TEAM 새 상태 시스템을 만들지 않는다(§16).
        self.revision_orchestration_service.stage_changed.connect(self._on_orchestration_stage_changed)
        return self.revision_orchestration_service

    def _on_revision_orchestration_result(self, result: OrchestrationResult):
        step = self._revision_original_step
        dev_result = self._revision_original_dev_result
        plan = self._revision_original_plan
        revision_plan = self._revision_plan
        if step is None or dev_result is None or plan is None or revision_plan is None:
            return

        pending_step_result = result.completed_steps[-1] if result.completed_steps else None

        if result.status == "waiting_for_approval" and pending_step_result is not None:
            # 38단계 §9 - 수정 development 실행 전 승인도 기존 project
            # checkpoint Dialog를 그대로 재사용한다(새 승인 시스템 아님).
            revision_step = self._find_plan_step(revision_plan, pending_step_result.step_id)
            if revision_step is None:
                self._fail_revision_and_restore(step, dev_result, plan, "수정 계획을 확인할 수 없습니다.")
                return

            approved = self._show_project_checkpoint_approval_dialog(
                revision_step, pending_step_result.approval_reason
            )
            if not approved:
                self.developer_status_label.setText("결과 검토 대기")
                self.work_step_value_label.setText("프로젝트 결과 검토 대기")
                self._present_development_review(step, dev_result, plan)
                return

            self.developer_status_label.setText("수정 중")
            self.work_step_value_label.setText("수정 작업 중")
            revision_orchestration_service = self._ensure_revision_orchestration_service(dev_result.project_path)
            if revision_orchestration_service is None:
                return
            revision_orchestration_service.resume_project_checkpoint(
                revision_plan, result.completed_steps, revision_step.step_id
            )
            return

        if result.status == "waiting_for_review" and pending_step_result is not None:
            # 38단계 §12 - 수정 development 성공. 원래 project plan의
            # 해당 step_id 결과를 새 DeveloperResult로 교체하고(§8 - 원본
            # plan.steps는 건드리지 않는다), 37단계 검토 화면을 그대로
            # 다시 보여준다(실행해서 확인/계속 진행/수정 요청 모두 다시
            # 가능).
            new_dev_result = pending_step_result.result
            self._apply_revision_result_to_original_plan(step.step_id, new_dev_result)

            # 39단계 §5/§7 - revision "후" 파일 목록을 다시 읽어 "전"과
            # 비교한다. 새 AI 호출 없이 규칙 기반으로만 요약을 만든다.
            # 이번 revision 하나에 대한 요약만 저장한다(§10 - 다음
            # revision이 시작되면 그때 다시 덮어써진다).
            after_files = self._safe_list_project_files(new_dev_result.project_path)
            self._revision_last_summary = build_revision_summary(
                requested_change=self._revision_user_request_text or "",
                new_dev_result_modified_files=list(new_dev_result.modified_files),
                before_files=self._revision_before_files,
                after_files=after_files,
            )

            # 41단계 §11 - revision으로 completed_steps 내용이 바뀌었으니
            # (원래 step_id의 result가 교체됨) 저장 상태도 갱신한다.
            self._save_active_project_state()

            self.developer_status_label.setText("결과 검토 대기")
            self.work_step_value_label.setText("프로젝트 결과 검토 대기")
            QMessageBox.information(self, "수정 완료", "수정 작업이 완료되었습니다.")
            self._present_development_review(step, new_dev_result, plan)
            return

        if result.status == "completed":
            # development 없이 analysis만으로 끝난 경우(코드 수정이
            # 필요 없다고 판단했거나, 이미 waiting_for_review로 처리된
            # development를 제외한 나머지가 정상 종료된 경우) - 원래
            # review 상태로 그대로 복귀한다.
            self.developer_status_label.setText("결과 검토 대기")
            self.work_step_value_label.setText("프로젝트 결과 검토 대기")
            QMessageBox.information(self, "수정 완료", result.summary)
            self._present_development_review(step, dev_result, plan)
            return

        # failed/blocked - §17: project 전체를 죽이지 않고 원래
        # review 상태로 복귀한다.
        self._fail_revision_and_restore(step, dev_result, plan, result.summary)

    def _on_revision_orchestration_error(self, message: str):
        step = self._revision_original_step
        dev_result = self._revision_original_dev_result
        plan = self._revision_original_plan
        if step is not None and dev_result is not None and plan is not None:
            self._fail_revision_and_restore(step, dev_result, plan, message)

    def _fail_revision_and_restore(
        self, step: BrainTaskStep, dev_result: DeveloperResult, plan: ChiefBrainPlan, message: str
    ):
        self.developer_status_label.setText("결과 검토 대기")
        self.work_step_value_label.setText("프로젝트 결과 검토 대기")
        QMessageBox.warning(self, "수정 실패", message)
        self._present_development_review(step, dev_result, plan)

    @staticmethod
    def _apply_revision_result(
        completed_steps: list[OrchestrationStepResult], original_step_id: str, new_dev_result: DeveloperResult
    ) -> list[OrchestrationStepResult]:
        """38단계 §8 - 원래 project plan의 completed_steps 안에서
        original_step_id 항목 하나만 새 DeveloperResult로 교체한다.
        원본 step_id/task_type/requires_approval/approval_reason은
        그대로 유지한다 - 이후 resume_after_review()가 같은 step_id로
        "이미 처리됨"을 인식해 재실행하지 않도록 하기 위해서다. 이 계획의
        steps 자체(BrainTaskStep 목록)는 이 함수가 아예 알지도 못한다 -
        여기서 다루는 건 실행 "결과" 데이터뿐이다.
        """
        updated: list[OrchestrationStepResult] = []
        for entry in completed_steps:
            if entry.step_id == original_step_id:
                entry = OrchestrationStepResult(
                    step_id=entry.step_id,
                    task_type=entry.task_type,
                    status="completed",
                    task_id=entry.task_id,
                    result=new_dev_result,
                    error=None,
                    requires_approval=entry.requires_approval,
                    approval_reason=entry.approval_reason,
                )
            updated.append(entry)
        return updated

    def _apply_revision_result_to_original_plan(self, original_step_id: str, new_dev_result: DeveloperResult):
        if self._last_orchestration_result is None:
            return

        updated_steps = self._apply_revision_result(
            self._last_orchestration_result.completed_steps, original_step_id, new_dev_result
        )
        self._last_orchestration_result = OrchestrationResult(
            status=self._last_orchestration_result.status,
            completed_steps=updated_steps,
            pending_step_id=self._last_orchestration_result.pending_step_id,
            summary=self._last_orchestration_result.summary,
        )

    def _find_project_path_from_completed_steps(self) -> str | None:
        """41단계 - 지금까지 완료된 step 중 실제 project_path를 가진
        결과(DeveloperResult)를 뒤에서부터 찾는다(duck typing, 기존
        step_context.py/화면 표시 코드와 동일한 방식) - project_path를
        새 필드로 어딘가에 별도 보관하지 않는다.
        """
        if self._last_orchestration_result is None:
            return None
        for entry in reversed(self._last_orchestration_result.completed_steps):
            project_path = getattr(entry.result, "project_path", None)
            if project_path:
                return project_path
        return None

    def _save_active_project_state(self) -> bool:
        """41단계 §11/§12 - project 모드 대형 프로젝트의 상태 변화 지점에서만
        호출되는 공통 저장 로직. task 모드거나(execution_mode != "project")
        아직 project plan이 없으면(_active_project_id is None) 아무 것도
        하지 않는다. 저장 실패는 §18에 따라 앱을 죽이지 않고 상태
        표시줄에만 짧게 알린다(팝업으로 자동 저장 흐름을 막지 않는다).
        """
        if self._active_project_id is None or self._current_chief_plan is None:
            return False
        if self._current_chief_plan.execution_mode != "project":
            return False

        try:
            state = create_project_state(
                plan=self._current_chief_plan,
                orchestration_result=self._last_orchestration_result,
                project_path=self._find_project_path_from_completed_steps(),
                last_user_request=self._revision_user_request_text,
                project_id=self._active_project_id,
                project_name=self._active_project_name,
                created_at=self._active_project_created_at,
            )
            self.project_state_store.save(state)
        except ProjectStateError:
            self.work_step_value_label.setText("프로젝트 상태 저장 실패")
            return False

        self._active_project_created_at = state.created_at
        return True

    def _on_save_project_button_clicked(self):
        """41단계 §13 - 자동 저장 훅과 별개로, 사용자가 명시적으로 지금
        상태를 저장하고 싶을 때 누르는 최소 버튼이다.
        """
        if self._active_project_id is None:
            QMessageBox.information(self, "프로젝트 저장", "현재 저장할 수 있는 대형 프로젝트가 없습니다.")
            return

        if self._save_active_project_state():
            QMessageBox.information(self, "프로젝트 저장", "현재 프로젝트 상태를 저장했습니다.")
        else:
            QMessageBox.warning(self, "프로젝트 저장 실패", "프로젝트 상태를 저장하지 못했습니다.")

    def _on_load_project_button_clicked(self):
        try:
            states = self.project_state_store.list_projects()
        except ProjectStateError as exc:
            QMessageBox.warning(self, "불러오기 실패", str(exc))
            return

        if not states:
            QMessageBox.information(self, "프로젝트 불러오기", "저장된 프로젝트가 없습니다.")
            return

        selected = self._show_project_load_list_dialog(states)
        if selected is None:
            return

        self._show_loaded_project_info_dialog(selected)

    def _show_project_load_list_dialog(self, states: list[PersistentProjectState]) -> PersistentProjectState | None:
        """41단계 §13 - 대형 Project Manager가 아니라, 이름/마지막 수정
        시간/현재 상태만 구분할 수 있는 최소 목록이다.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("프로젝트 불러오기")

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("불러올 프로젝트를 선택하세요:"))

        list_widget = QListWidget()
        for state in states:
            status_text = self._ORCHESTRATION_STATUS_LABELS.get(state.orchestration_status, state.orchestration_status)
            item = QListWidgetItem(f"{state.project_name}  [{status_text}]  ({state.updated_at})")
            item.setData(Qt.ItemDataRole.UserRole, state.project_id)
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        button_row = QHBoxLayout()
        select_button = QPushButton("선택")
        cancel_button = QPushButton("취소")
        button_row.addWidget(select_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        select_button.clicked.connect(lambda: dialog.done(1))
        cancel_button.clicked.connect(lambda: dialog.done(0))
        cancel_button.setDefault(True)
        cancel_button.setFocus()

        if dialog.exec() != 1 or list_widget.currentItem() is None:
            return None

        selected_project_id = list_widget.currentItem().data(Qt.ItemDataRole.UserRole)
        try:
            return self.project_state_store.load(selected_project_id)
        except ProjectStateError as exc:
            QMessageBox.warning(self, "불러오기 실패", str(exc))
            return None

    def _show_loaded_project_info_dialog(self, state: PersistentProjectState):
        """41단계 §14/§19 - 불러오기 자체는 실행 명령이 아니다(중요).
        상태만 보여주고, 사용자가 명시적으로 "이어서 진행"을 눌러야만
        기존 승인/검토 흐름(_resume_loaded_project)으로 넘어간다.
        """
        total_steps = len(state.plan.steps)
        completed_count = sum(1 for s in state.completed_steps if s.status == "completed")
        current_step = self._find_plan_step(state.plan, state.current_step_id) if state.current_step_id else None
        current_step_text = current_step.title if current_step is not None else "없음"
        status_text = self._ORCHESTRATION_STATUS_LABELS.get(state.orchestration_status, state.orchestration_status)

        dialog = QDialog(self)
        dialog.setWindowTitle("프로젝트 상태")

        layout = QVBoxLayout(dialog)
        message = QLabel(
            f"프로젝트 이름:\n{state.project_name}\n\n"
            f"현재 상태:\n{status_text}\n\n"
            f"완료 단계:\n{completed_count} / {total_steps}\n\n"
            f"현재/다음 단계:\n{current_step_text}\n\n"
            f"마지막 사용자 요청:\n{state.last_user_request or '없음'}\n\n"
            "이전 화면 이미지는 세션 종료로 복구되지 않았습니다."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        button_row = QHBoxLayout()
        resume_button = QPushButton("이어서 진행")
        close_button = QPushButton("닫기")
        button_row.addWidget(resume_button)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

        resume_button.clicked.connect(lambda: dialog.done(1))
        close_button.clicked.connect(lambda: dialog.done(0))
        close_button.setDefault(True)
        close_button.setFocus()

        if dialog.exec() == 1:
            self._resume_loaded_project(state)

    def _resume_loaded_project(self, state: PersistentProjectState):
        """41단계 §15 - 새 Orchestrator를 만들지 않는다. 내부 상태만
        복구한 뒤 기존 handler(_handle_project_checkpoint_approval/
        _handle_development_review)로 그대로 넘긴다 - 그 handler들이
        부르는 resume_project_checkpoint()/resume_after_review()가 이미
        "step_id가 completed_steps에 있으면 재실행하지 않는다"는 규칙을
        갖고 있으므로(round34/36에서 이미 검증됨) 여기서 새로 만들
        필요가 없다.
        """
        self._current_chief_plan = state.plan
        self._active_project_id = state.project_id
        self._active_project_name = state.project_name
        self._active_project_created_at = state.created_at
        # OrchestrationResult.status는 StepStatus라 "not_started"를 표현할
        # 수 없다 - 아직 아무 step도 실행된 적이 없다는 뜻이므로
        # "completed"(할 일 없음)와 동일하게 다룬다.
        restored_status = state.orchestration_status if state.orchestration_status != "not_started" else "completed"
        self._last_orchestration_result = OrchestrationResult(
            status=restored_status,
            completed_steps=state.completed_steps,
            pending_step_id=state.current_step_id,
            summary=state.waiting_reason or "",
        )

        pending_step_result = state.completed_steps[-1] if state.completed_steps else None

        if state.orchestration_status == "waiting_for_approval" and pending_step_result is not None:
            self._handle_project_checkpoint_approval(pending_step_result)
            return

        if state.orchestration_status == "waiting_for_review" and pending_step_result is not None:
            self._handle_development_review(pending_step_result)
            return

        if state.orchestration_status == "completed":
            QMessageBox.information(self, "프로젝트 불러오기", "이미 완료된 프로젝트입니다.")
            return

        QMessageBox.information(
            self,
            "프로젝트 불러오기",
            "이 상태(실행기 없음/실패/중단/시작 전)는 이번 버전에서 자동으로 이어서 "
            "진행할 수 없습니다. 상태 정보만 복구되었습니다.",
        )

    def _on_rerun_research_analysis_button_clicked(self):
        """45단계 §11/§18 - project mode + 저장된 project에서만 동작한다.

        task mode거나 아직 대형 project가 없으면(§1/§11) 명확히 안내만
        하고 아무것도 하지 않는다. 다시 실행할 완료된 research 결과가
        없어도(예: 아직 research 전이거나 실패만 있는 경우) 마찬가지로
        안내만 한다 - 없는 대상을 지어내 재실행하지 않는다.
        """
        if (
            self._active_project_id is None
            or self._current_chief_plan is None
            or self._current_chief_plan.execution_mode != "project"
            or self._last_orchestration_result is None
        ):
            QMessageBox.information(self, "조사/분석 다시 실행", "현재 다시 실행할 수 있는 대형 프로젝트가 없습니다.")
            return

        root_step_ids = find_rerun_root_step_ids(self._last_orchestration_result.completed_steps)
        if not root_step_ids:
            QMessageBox.information(self, "조사/분석 다시 실행", "다시 실행할 조사 결과가 없습니다.")
            return

        if not self._show_project_stage_rerun_confirm_dialog():
            return

        affected_step_ids = compute_affected_step_ids(self._current_chief_plan, root_step_ids)
        candidate_completed_steps = build_rerun_candidate_completed_steps(
            self._last_orchestration_result.completed_steps, affected_step_ids
        )

        rerun_orchestration_service = self._ensure_rerun_orchestration_service()
        if rerun_orchestration_service is None:
            return

        self.rerun_research_analysis_button.setEnabled(False)
        self.work_step_value_label.setText("조사/분석 다시 실행 중")
        rerun_orchestration_service.resume_after_review(self._current_chief_plan, candidate_completed_steps)

    def _show_project_stage_rerun_confirm_dialog(self) -> bool:
        """45단계 §10 - 버튼 클릭 즉시 실행하지 않는다. 취소하면 아무것도
        바꾸지 않는다(호출자가 dialog.exec() 결과만 보고 판단한다).
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("조사/분석 다시 실행")

        layout = QVBoxLayout(dialog)
        message = QLabel(
            "기존 조사/분석 결과를 최신 Studio 기능으로 다시 실행합니다.\n\n"
            "기존 프로젝트 계획은 유지됩니다.\n"
            "재실행에 성공하면 기존 조사/분석 결과가 새 결과로 교체됩니다.\n"
            "실패하면 기존 저장 상태를 유지합니다."
        )
        message.setWordWrap(True)
        layout.addWidget(message)

        button_row = QHBoxLayout()
        rerun_button = QPushButton("다시 실행")
        cancel_button = QPushButton("취소")
        button_row.addWidget(rerun_button)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        rerun_button.clicked.connect(dialog.accept)
        cancel_button.clicked.connect(dialog.reject)
        cancel_button.setDefault(True)
        cancel_button.setFocus()

        return dialog.exec() == QDialog.DialogCode.Accepted

    def _ensure_rerun_orchestration_service(self) -> OrchestrationService | None:
        """45단계 §12 - 기존 orchestration_service/revision_orchestration_service와
        동일한 Provider 조합을 그대로 재사용한다(새 Research/Analysis/
        Development Provider를 만들지 않는다). 원래 project plan 실행에
        쓰는 orchestration_service와 완전히 분리된 인스턴스다(37/38단계와
        동일한 이유 - Qt Signal 교차 오염 방지).
        """
        task_system = self._ensure_task_system()
        if task_system is None:
            return None

        development_executor = DevelopmentExecutor(OpenAIDeveloperProvider())
        reviewer_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        analysis_executor = AnalysisExecutor(OpenAIResearchReviewerProvider(reviewer_client))
        orchestrator = ChiefBrainOrchestrator(
            task_system, development_executor=development_executor, analysis_executor=analysis_executor
        )

        self.rerun_orchestration_service = OrchestrationService(orchestrator, parent=self)
        self.rerun_orchestration_service.result_ready.connect(self._on_project_stage_rerun_result)
        self.rerun_orchestration_service.error_occurred.connect(self._on_project_stage_rerun_error)
        self.rerun_orchestration_service.stage_changed.connect(self._on_orchestration_stage_changed)
        return self.rerun_orchestration_service

    def _on_project_stage_rerun_result(self, result: OrchestrationResult):
        """45단계 §5~§7/§15/§20 - 성공했을 때만 self._last_orchestration_result/
        영구 저장을 새 결과로 갱신한다. 실패(failed/blocked/
        waiting_for_executor)면 기존 메모리 상태/저장 JSON을 그대로 두고
        안내만 한다(§7 - traceback 노출 없이 명확한 문장 하나만).
        """
        self.rerun_research_analysis_button.setEnabled(True)

        if result.status in ("failed", "blocked", "waiting_for_executor"):
            self.work_step_value_label.setText("조사/분석 재실행 실패 - 기존 상태 유지")
            QMessageBox.warning(
                self, "조사/분석 다시 실행 실패", "단계 재실행에 실패하여 기존 프로젝트 상태를 유지했습니다."
            )
            return

        # §20 - memory(self._last_orchestration_result)와 persistent
        # state(project_state_store)가 서로 다른 결과를 갖지 않도록 항상
        # 함께, 성공한 최신 결과로만 갱신한다.
        self._last_orchestration_result = result
        self._save_active_project_state()

        pending_step_result = result.completed_steps[-1] if result.completed_steps else None

        if result.status == "waiting_for_approval" and pending_step_result is not None:
            # §8/§13/§19 - 새 승인 시스템을 만들지 않는다. 34/42단계
            # 기존 project 체크포인트 흐름을 그대로 재사용한다 - 이
            # Dialog가 self._last_orchestration_result.completed_steps
            # (이미 위에서 최신 결과로 교체됨)를 그대로 읽으므로 새
            # Research/Analysis 결과가 자동으로 표시된다.
            self.work_step_value_label.setText("최신 조사/분석 반영 완료 - 개발 승인 대기")
            self._handle_project_checkpoint_approval(pending_step_result)
            return

        if result.status == "waiting_for_review" and pending_step_result is not None:
            self.work_step_value_label.setText("최신 조사/분석 반영 완료 - 개발 결과 검토 대기")
            self._handle_development_review(pending_step_result)
            return

        self.work_step_value_label.setText("최신 조사/분석 반영 완료")
        self._show_orchestration_result_dialog(result)

    def _on_project_stage_rerun_error(self, message: str):
        """45단계 §7 - 예상치 못한 예외도 rollback과 동일하게 처리한다
        (내부 traceback을 그대로 노출하지 않는다)."""
        self.rerun_research_analysis_button.setEnabled(True)
        self.work_step_value_label.setText("조사/분석 재실행 실패 - 기존 상태 유지")
        QMessageBox.warning(
            self, "조사/분석 다시 실행 실패", "단계 재실행에 실패하여 기존 프로젝트 상태를 유지했습니다."
        )

    def _show_orchestration_result_dialog(self, result: OrchestrationResult):
        plan = self._current_chief_plan
        objective = plan.objective if plan else ""

        step_blocks = []
        for order, step_result in enumerate(result.completed_steps, start=1):
            status_text = self._ORCHESTRATION_STATUS_LABELS.get(step_result.status, step_result.status)
            lines = [f"{order}. [{step_result.task_type}] {step_result.step_id} - {status_text}"]

            if step_result.status == "completed" and step_result.task_type == "research":
                lines.append("   검색 완료")
            elif step_result.status == "completed" and step_result.task_type == "development":
                dev_result = step_result.result
                created_files = "\n".join(f"   - {name}" for name in getattr(dev_result, "created_files", []) or [])
                lines.append(f"   생성 프로젝트: {getattr(dev_result, 'project_path', '')}")
                lines.append(f"   entry_point: {getattr(dev_result, 'entry_point', '')}")
                lines.append(f"   생성 파일:\n{created_files or '   (없음)'}")
            elif step_result.status == "completed" and step_result.task_type == _SCREEN_OBSERVATION_TASK_TYPE:
                obs_result = step_result.result
                observations = "\n".join(f"   - {item}" for item in getattr(obs_result, "observations", []) or [])
                issues = "\n".join(f"   - {item}" for item in getattr(obs_result, "issues", []) or [])
                lines.append(f"   요약: {getattr(obs_result, 'summary', '')}")
                lines.append(f"   관찰:\n{observations or '   (없음)'}")
                lines.append(f"   문제:\n{issues or '   (없음)'}")
                lines.append(f"   다음 행동: {getattr(obs_result, 'next_action', '')}")
            elif step_result.status == "waiting_for_executor":
                lines.append("   현재 이 단계의 실행 기능이 아직 연결되지 않았습니다.")
            elif step_result.status == "waiting_for_approval":
                lines.append(f"   승인이 필요합니다: {step_result.approval_reason or ''}")
            elif step_result.status == "failed":
                lines.append(f"   오류: {step_result.error or ''}")
            elif step_result.status == "blocked":
                lines.append(f"   {step_result.error or ''}")

            step_blocks.append("\n".join(lines))

        message = (
            f"전체 목표:\n{objective}\n\n"
            f"단계별 결과:\n" + "\n\n".join(step_blocks) + "\n\n"
            f"최종 상태: {self._ORCHESTRATION_STATUS_LABELS.get(result.status, result.status)}\n"
            f"{result.summary}"
        )
        self._show_scrollable_result_dialog("업무 실행 결과", message)
