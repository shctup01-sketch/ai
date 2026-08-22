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
    """


class AnalysisExecutor:
    """BrainTaskStep -> ResearchReviewRequest 변환 후 ResearchReviewerProvider.review()를 호출한다."""

    def __init__(self, reviewer_provider: ResearchReviewerProvider):
        self._reviewer_provider = reviewer_provider

    def execute(self, step: BrainTaskStep, context: ExecutionContext | None = None) -> ResearchReviewResult:
        request = self._build_request(step, context)

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
            else:
                lines.append(f"  {dep_id}: 지원하지 않는 dependency 결과 형태")

        return "\n".join(lines)

    @staticmethod
    def _build_request(step: BrainTaskStep, context: ExecutionContext | None) -> ResearchReviewRequest:
        dependencies = context.dependencies if context is not None else []
        query, search_results = _merge_research_dependencies(dependencies)
        dependency_context = _merge_analysis_dependencies(dependencies)
        return ResearchReviewRequest(
            task_title=step.title,
            task_goal=step.goal,
            query=query,
            search_results=search_results,
            dependency_context=dependency_context,
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


def _merge_analysis_dependencies(dependencies: list[StepContext]) -> str:
    """analysis 모양(ResearchReviewResult 구조)인 dependency들의 summary를
    순서를 유지하며 하나로 합친다(48단계, Analysis -> Analysis).

    summary는 ResearchReviewResult가 실제로 갖고 있는 필드다(지어낸
    필드가 아니다) - market_observations/candidate_ideas 등 나머지
    필드까지 전부 옮기지는 않는다(§4 - 최소 지원, 새 거대한 Context
    시스템을 만들지 않는다). research가 아닌 다른 모양(예: development
    결과)의 dependency는 여기서도 건너뛴다 - 가짜 내용을 지어내지 않는다.
    """
    parts: list[str] = []
    for dep in dependencies:
        if _is_analysis_result_shaped(dep.result):
            parts.append(f"[{dep.step_id}] {dep.result.summary}")
    return "\n\n".join(parts)
