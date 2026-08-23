"""BrainTaskStep(task_type="analysis")을 기존 Reviewer 실행 경로로 연결하는 어댑터.

새 분석 AI를 만들지 않는다 - 이미 검증된 Research Reviewer(단일 Research
UI 흐름에서 "조사 결과 분석"에 쓰이는 것과 동일한 ResearchReviewerProvider
계약)를 그대로 재사용한다. ResearchReviewService(QThread/UI 계층)는
전혀 의존하지 않는다 - 이 파일은 DevelopmentExecutor와 같은 순수 실행
계층이다.

analysis step은 자신의 depends_on(ExecutionContext)에서 "완료된" research
결과만 받아 기존 ResearchReviewRequest로 변환한다. dependency가 여러
개면(예: research A, research B에 모두 의존) 각 결과의 query/search_results를
순서를 유지하며 하나로 합친다 - 새 Request 모델을 만들지 않고 기존
ResearchReviewRequest(search_results: list[dict])를 그대로 재사용한다.
원본 dependency의 dict/list는 절대 제자리에서 수정하지 않고, 합쳐진
새 리스트에만 항목을 복사해 담는다. 각 검색 결과가 어느 dependency
step에서 왔는지 구분할 수 있도록, 복사본의 title 앞에만
"[step_id] "를 붙인다(원본 title도, 검색 결과 자체의 사실 내용도 바꾸지
않는다 - 가짜 정보를 만들어 넣지 않는다).

48단계 - depends_on 중 "analysis 모양"(ResearchReviewResult가 실제로
갖고 있는 필드 구조 - summary/market_observations/candidate_ideas/
recommended_idea/recommendation_reason/risks/next_action) 결과는 이제
버리지 않는다. research 모양과 완전히 별도로 병합해(ResearchReviewRequest.
dependency_context) 전달한다 - 두 모양이 섞여 있어도(Research + Analysis
동시 dependency) 각자 자기 자리로만 들어간다. 없는 필드를 지어내지
않는다 - 실제로 존재하는 summary 필드만 그대로 옮긴다.

52단계 - "development 모양"(DeveloperResult가 실제로 갖고 있는 필드
구조 - developer_result.py 정의 그대로: status/summary/project_path/
entry_point/created_files/modified_files/errors) 결과도 같은 방식으로
지원한다. Research → Analysis → Development → Analysis 같은 실제 장기
개발 루프에서 "이전 Development 결과"를 검토하는 Analysis가 실제로
필요했다(실기 GameBlock 프로젝트에서 확인된 실패). 새 필드를 추가하지
않고 기존 dependency_context를 그대로 확장한다(§8) - analysis 모양과
development 모양 dependency 모두 depends_on 순서를 유지하며 같은
dependency_context 문자열에 담기되, 각자 자기 헤더
("[이전 분석: step_id]" / "[이전 개발 결과: step_id]") 아래로만
들어가 서로 섞이지 않는다.
"""

from .brain_task_step import BrainTaskStep
from .research_review_request import ResearchReviewRequest
from .research_review_result import ResearchReviewResult
from .research_reviewer_provider import ResearchReviewerProvider
from .step_context import ExecutionContext, StepContext


class AnalysisExecutionError(Exception):
    """AnalysisExecutor가 Reviewer 실행을 완료하지 못했을 때 발생한다.

    ResearchReviewerProvider.review()가 던지는 RuntimeError(API Key
    누락/인증 실패/네트워크 오류 등)를 가짜 success로 둔갑시키지 않고,
    호출자(Orchestrator)가 명확히 구분해 처리할 수 있는 단일 예외
    타입으로 감싼다. KeyboardInterrupt/SystemExit는 Exception이 아니라
    여기서 잡히지 않고 그대로 전파된다.

    43단계 - depends_on이 있는데도 병합된 search_results가 0건이면
    (선행 research 결과가 이 step에 제대로 연결되지 않았을 가능성이 큼)
    이 예외를 그대로 재사용해 "완료"가 아니라 "실패"로 처리한다 - 새
    상태를 만들지 않고, Orchestrator가 이미 하던 처리(실패 시 그 자리에서
    중단하고 development로 넘어가지 않음)를 그대로 재사용한다.

    47단계 - 이 메시지를 depends_on/실제 확인된 dependency별 결과
    건수까지 담도록 확장했다(§3). "0건"이라는 사실만으로는 원인이
    (CASE2) depends_on 대상이 애초에 completed_steps에 없었는지,
    (CASE3) 있었지만 그 research 자체가 0건이었는지, (CASE4) 있었지만
    research 모양이 아니었는지 구분할 수 없었다 - 새 Error 모델을
    만들지 않고 이 예외의 메시지 문자열만 더 자세하게 채운다.

    48단계 - "research 모양이 아니면 무조건 CASE4(지원 안 함)"이던 판정을
    바꿨다. analysis 모양(ResearchReviewResult 구조)인 dependency는 이제
    정상적으로 사용 가능하므로, search_results/dependency_context가 모두
    비어 있을 때만(둘 다 usable 결과가 없을 때만) 이 예외가 발생한다.

    52단계 - development 모양(DeveloperResult 구조)인 dependency도
    dependency_context에 담기므로(§6 - "이미 존재하는 dependency_context를
    안전하게 확장") 이 실패 조건 자체는 수정할 필요가 없었다 -
    usable_research_results/usable_analysis_context/usable_development_
    context 중 하나라도 있으면 통과해야 한다는 요구사항이 이미 만족된다.
    """


class AnalysisExecutor:
    """BrainTaskStep -> ResearchReviewRequest 변환 후 ResearchReviewerProvider.review()를 호출한다.

    57단계 - product_context_text(프로젝트의 승인된 장기 제품 기준,
    project_product_context.py)는 depends_on/ExecutionContext를 거치지
    않는다. depends_on은 "이 step이 직접 참고할 선행 결과"만 담는
    자리이고, 장기 제품 기준은 project 전체에 걸친 값이라 매 step의
    depends_on 목록에 넣을 대상이 아니다 - 대신 이 Executor 자신이
    들고 있다가 매 review() 호출마다 함께 보낸다(생성자 기본값/
    set_product_context_text()로만 갱신, Orchestrator/OrchestrationService의
    기존 시그니처는 전혀 바꾸지 않는다).
    """

    def __init__(self, reviewer_provider: ResearchReviewerProvider, product_context_text: str = ""):
        self._reviewer_provider = reviewer_provider
        self._product_context_text = product_context_text

    def set_product_context_text(self, product_context_text: str) -> None:
        """57단계 - 호출자(main_window.py)가 최신 Project Product Context
        요약 텍스트로 갱신할 때 쓴다. 이 Executor 인스턴스가 재사용되는
        동안(예: 메인 orchestration_service의 guarded singleton) 사용자가
        나중에 제품 기준을 설정/수정해도 다음 review() 호출부터 바로
        반영되도록 한다 - 생성 시점에만 값이 고정되면 이후 변경이 계속
        무시되는 오래된 값(staleness) 문제가 생긴다.
        """
        self._product_context_text = product_context_text

    def execute(self, step: BrainTaskStep, context: ExecutionContext | None = None) -> ResearchReviewResult:
        request = self._build_request(step, context, self._product_context_text)

        # 43단계 §9 - depends_on을 선언했다는 것은 "선행 결과를 참고해야
        # 한다"는 뜻인데, 병합 결과가 아무것도 없으면 그 연결이 실제로는
        # 끊어져 있었다는 뜻이다. depends_on이 애초에 없는 step(기존
        # 25단계 AE 케이스 - 선행 결과 없이도 동작하는 독립 analysis)까지
        # 막으면 기존 기능을 깨뜨리므로, depends_on이 있을 때만 검사한다.
        # 48단계 §7 - "search_results가 0건이면 실패"이던 기준을 바꿨다.
        # Analysis -> Analysis에서는 search_results가 원래도 0건이면서
        # dependency_context(이전 analysis 요약)만 있는 게 정상이다 -
        # 그래서 "둘 다" 비어 있을 때만 실패로 본다.
        if step.depends_on and not request.search_results and not request.dependency_context:
            raise AnalysisExecutionError(self._build_empty_dependency_message(step, context))

        try:
            return self._reviewer_provider.review(request)
        except Exception as exc:
            raise AnalysisExecutionError(str(exc)) from exc

    @staticmethod
    def _build_empty_dependency_message(step: BrainTaskStep, context: ExecutionContext | None) -> str:
        """47단계 §3 - depends_on 각 항목이 실제로 어떤 상태였는지
        진단 가능한 문장으로 풀어낸다. dependencies는 이미
        chief_brain_orchestrator.py._build_execution_context()가
        "completed 상태의 depends_on 대상만" 골라 넣어둔 것이므로,
        여기 없는 step_id는 곧 "completed_steps에서 찾지 못했다"는
        뜻이다(CASE2) - 있는데 research/analysis 어느 모양도 아니면
        지원하지 않는 형태, 있고 research 모양인데 0건이면 CASE3이다.
        추측 없이 실제로 받은 depends_on/dependencies만 본다.

        48단계 §9 - analysis 모양(ResearchReviewResult 구조)인
        dependency는 더 이상 "형태가 아님" 오류로 표시하지 않고
        "analysis 결과 사용 가능"으로 정확히 구분한다.

        52단계 §10 - development 모양(DeveloperResult 구조)인
        dependency도 같은 방식으로 "지원하지 않는 형태"가 아니라
        "development 결과 사용 가능"으로 정확히 구분한다. 파일 개수
        (생성/수정) 정도만 덧붙인다 - summary 원문이나 내부 경로를
        그대로 노출하지 않는다(과도한 내부 정보 출력 금지).
        """
        dependencies = context.dependencies if context is not None else []
        present_by_id = {dep.step_id: dep for dep in dependencies}

        lines = [
            "분석에 참고할 이전 단계 결과를 찾지 못했습니다"
            "(사용 가능한 조사 결과/이전 분석 내용이 모두 없음).",
            f"analysis_step={step.step_id}",
            f"depends_on={step.depends_on}",
            "확인된 dependency:",
        ]
        for dep_id in step.depends_on:
            dep = present_by_id.get(dep_id)
            if dep is None:
                lines.append(f"  {dep_id}: 결과를 찾을 수 없음(완료되지 않았거나 이 단계에 연결되지 않음)")
                continue
            result = dep.result
            if isinstance(result, dict) and "search_results" in result:
                count = len(result.get("search_results") or [])
                lines.append(f"  {dep_id}: research 결과 {count}건")
            elif _is_analysis_result_shaped(result):
                lines.append(f"  {dep_id}: analysis 결과 사용 가능")
            elif _is_development_result_shaped(result):
                created_count = len(result.created_files)
                modified_count = len(result.modified_files)
                lines.append(f"  {dep_id}: development 결과 사용 가능(생성 {created_count}건, 수정 {modified_count}건)")
            else:
                lines.append(f"  {dep_id}: 지원하지 않는 dependency 결과 형태")

        return "\n".join(lines)

    @staticmethod
    def _build_request(
        step: BrainTaskStep, context: ExecutionContext | None, product_context_text: str = ""
    ) -> ResearchReviewRequest:
        """57단계 - product_context_text를 세 번째 인자로 추가하되 기본값을
        빈 문자열로 둔다. 이 메서드를 여전히 @staticmethod로 두고 인자
        하나만 늘린 이유는, 기존 test_round49_chained_analysis_context.py가
        이 메서드를 `AnalysisExecutor._build_request(step, context)`처럼
        인스턴스 없이 2-인자로 직접 호출하기 때문이다(직접 확인) - 이
        메서드를 인스턴스 메서드로 바꾸면 그 기존 테스트 호출부가 전부
        깨진다. 기본값 있는 인자 추가만으로 기존 호출부를 전혀 건드리지
        않고도 새 기능을 더할 수 있다.
        """
        dependencies = context.dependencies if context is not None else []
        query, search_results = _merge_research_dependencies(dependencies)
        dependency_context = _merge_dependency_context(dependencies)
        return ResearchReviewRequest(
            task_title=step.title,
            task_goal=step.goal,
            query=query,
            search_results=search_results,
            dependency_context=dependency_context,
            product_context=product_context_text,
        )


# 48단계 - ResearchReviewResult가 실제로 갖고 있는 필드만 나열한다
# (research_review_result.py 정의 그대로) - 구체 클래스를 import하지
# 않고 duck typing만으로 판단한다(step_context.py의
# _is_research_review_shaped와 동일한 방식, 이 파일 자신의 기존 관례를
# 따라 자체적으로 둔다 - analysis_executor.py는 이미 research 모양
# 판정도 다른 파일에 의존하지 않고 여기서 직접 한다).
_ANALYSIS_RESULT_SHAPE_ATTRS = (
    "summary",
    "market_observations",
    "candidate_ideas",
    "recommended_idea",
    "recommendation_reason",
    "risks",
    "next_action",
)


def _is_analysis_result_shaped(result: object) -> bool:
    return all(hasattr(result, attr) for attr in _ANALYSIS_RESULT_SHAPE_ATTRS)


# 52단계 - DeveloperResult가 실제로 갖고 있는 필드 중, ExecutionResult
# (execution_result.py, runtime 검토 전용 - project_path/entry_point는
# 있지만 created_files/modified_files는 없다)와 겹치지 않는 조합만
# 골라 판별한다. developer_result.py 정의 그대로다 - 없는 필드를
# 지어내지 않는다.
_DEVELOPMENT_RESULT_SHAPE_ATTRS = ("project_path", "entry_point", "created_files", "modified_files")


def _is_development_result_shaped(result: object) -> bool:
    return all(hasattr(result, attr) for attr in _DEVELOPMENT_RESULT_SHAPE_ATTRS)


def _merge_research_dependencies(dependencies: list[StepContext]) -> tuple[str, list[dict]]:
    """research 모양(dict에 search_results 키)인 dependency들의 query/search_results를 하나로 합친다.

    research 모양이 아닌 dependency(analysis 모양은 _merge_analysis_dependencies()가
    따로 처리한다, 48단계)는 검색 결과가 없으므로 건너뛴다 - 가짜
    search_results를 지어내지 않는다.
    """
    queries: list[str] = []
    merged_results: list[dict] = []

    for dep in dependencies:
        result = dep.result
        if not isinstance(result, dict) or "search_results" not in result:
            continue

        query = result.get("query", "")
        if query:
            queries.append(query)

        for item in result.get("search_results") or []:
            if not isinstance(item, dict):
                merged_results.append(item)
                continue
            copied = dict(item)
            title = copied.get("title", "")
            copied["title"] = f"[{dep.step_id}] {title}" if title else f"[{dep.step_id}]"
            merged_results.append(copied)

    return " / ".join(queries), merged_results


def _format_analysis_dependency(dep: StepContext) -> str:
    """49단계 §3 - analysis 모양(ResearchReviewResult 구조) dependency
    하나를 규칙 기반으로 구조화된 텍스트로 만든다(새 AI 요약 호출 없음).
    ResearchReviewResult가 실제로 갖고 있는 7개 필드(summary/
    market_observations/candidate_ideas/recommended_idea/
    recommendation_reason/risks/next_action)만 쓴다 - 없는 필드를
    지어내지 않는다. 값이 비어 있는 필드는 그 섹션 자체를 생략한다(§3 -
    "실제 값이 비어 있는 항목은 생략 가능").
    """
    result = dep.result
    sections = [f"[이전 분석: {dep.step_id}]"]

    if result.summary:
        sections.append(f"요약:\n{result.summary}")
    if result.market_observations:
        sections.append("관찰:\n" + "\n".join(f"- {item}" for item in result.market_observations))
    if result.candidate_ideas:
        sections.append("후보:\n" + "\n".join(f"- {item}" for item in result.candidate_ideas))
    if result.recommended_idea:
        sections.append(f"추천:\n{result.recommended_idea}")
    if result.recommendation_reason:
        sections.append(f"추천 이유:\n{result.recommendation_reason}")
    if result.risks:
        sections.append("위험:\n" + "\n".join(f"- {item}" for item in result.risks))
    if result.next_action:
        sections.append(f"다음 행동:\n{result.next_action}")

    return "\n\n".join(sections)


def _format_development_dependency(dep: StepContext) -> str:
    """52단계 §4 - development 모양(DeveloperResult 구조) dependency
    하나를 규칙 기반으로 구조화된 텍스트로 만든다(새 AI 요약 호출 없음).
    DeveloperResult가 실제로 갖고 있는 필드(summary/project_path/
    entry_point/created_files/modified_files/errors)만 쓴다 - 없는
    필드를 지어내지 않는다. 값이 비어 있는 필드는 그 섹션 자체를
    생략한다(_format_analysis_dependency와 동일한 관례). 전체 파일
    내용/소스코드 원문은 절대 옮기지 않는다(§4 - 파일 "이름"만 옮긴다).

    54단계 §9 - dep.result가 DevelopmentEvidenceSnapshot(DeveloperResult
    상속)이면, 실제로 존재하는 실행 검증/화면 검수/수정 이력 증거도
    이어서 붙인다. getattr(..., 기본값)으로 판별한다 - 순수
    DeveloperResult(evidence가 붙지 않은 과거 저장분/구버전 호환 결과)는
    getattr이 항상 기본값을 돌려주므로 이 블록에서 아무 것도 추가되지
    않는다(§AF - 하위 호환). "사용자 검수 완료"처럼 실제로 없는 사실을
    만들어 쓰지 않는다(§7) - visual_review_summary는 어디까지나 "Brain
    화면 분석" 결과로만 표시한다.
    """
    result = dep.result
    sections = [f"[이전 개발 결과: {dep.step_id}]"]

    if result.status:
        sections.append(f"개발 상태:\n{'성공' if result.status == 'success' else '실패'}")
    if result.summary:
        sections.append(f"개발 요약:\n{result.summary}")
    if result.project_path:
        sections.append(f"프로젝트 경로:\n{result.project_path}")
    if result.entry_point:
        sections.append(f"실행 진입점:\n{result.entry_point}")
    if result.created_files:
        sections.append("생성 파일:\n" + "\n".join(f"- {name}" for name in result.created_files))
    if result.modified_files:
        sections.append("수정 파일:\n" + "\n".join(f"- {name}" for name in result.modified_files))
    if result.errors:
        sections.append("오류:\n" + "\n".join(f"- {item}" for item in result.errors))

    if getattr(result, "runtime_checked", False):
        exec_lines = [f"실행 성공: {'예' if result.runtime_success else '아니오'}"]
        if result.runtime_summary:
            exec_lines.append(f"실행 결과:\n{result.runtime_summary}")
        sections.append("[실행 검증]\n" + "\n".join(exec_lines))

    if getattr(result, "visual_review_summary", None):
        visual_lines = [f"Brain 화면 분석:\n{result.visual_review_summary}"]
        if result.observed_features:
            visual_lines.append("관찰된 기능:\n" + "\n".join(f"- {item}" for item in result.observed_features))
        sections.append("[화면 검수]\n" + "\n".join(visual_lines))

    if getattr(result, "revision_requested", None) or getattr(result, "revision_summary", None):
        revision_lines = []
        if getattr(result, "revision_requested", None):
            revision_lines.append(f"수정 요청:\n{result.revision_requested}")
        if getattr(result, "revision_summary", None):
            revision_lines.append(f"수정 완료 요약:\n{result.revision_summary}")
        sections.append("[수정 이력]\n" + "\n".join(revision_lines))

    return "\n\n".join(sections)


def _merge_dependency_context(dependencies: list[StepContext]) -> str:
    """analysis 모양(ResearchReviewResult 구조)과 development 모양
    (DeveloperResult 구조) dependency를 depends_on에 적힌 순서 그대로
    하나로 합친다(52단계 §7 - 타입이 섞여 있어도 순서만 유지한 채 각자
    자기 헤더 아래로만 들어간다, 한 타입 때문에 다른 타입을 버리지
    않는다. 48/49단계에서 summary만 옮기던 것을 구조화된 전체 필드로
    확장했다, §3).

    research 모양은 여기서 다루지 않는다(_merge_research_dependencies가
    이미 search_results로 별도 처리한다) - 가짜 내용을 지어내지 않는다.
    원본 결과 객체는 읽기만 할 뿐 수정하지 않는다(§6).
    """
    parts: list[str] = []
    for dep in dependencies:
        if _is_analysis_result_shaped(dep.result):
            parts.append(_format_analysis_dependency(dep))
        elif _is_development_result_shaped(dep.result):
            parts.append(_format_development_dependency(dep))
    return "\n\n".join(parts)
