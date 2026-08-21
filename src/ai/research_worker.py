"""범용 Worker/Tool 구조 위의 첫 번째 실제 Worker.

ResearchWorker는 Task의 title/goal로 검색어를 만들고, WorkerContext를
통해 web_search Tool을 호출해 검색 결과를 그대로 담아 반환한다.
ToolExecutor/ToolRegistry/PermissionManager/WebSearchTool/
WebSearchProvider는 직접 알지 못한다 - Tool 호출은 오직 WorkerContext를
거친다. 승인 여부도 스스로 결정하지 않는다(approved를 임의로 True로
보내지 않음) - 그건 PermissionManager의 책임이다. 검색 결과를 요약하거나
market_size/competitors/recommendation 같은 분석 데이터를 만들어내지
않는다 - 그건 향후 별도의 분석 단계가 할 일이다.

44단계 - 넓은 조사 목표(title+goal 결합 기준 단어 수가 많은 경우)는 한 번의
검색으로 끝내지 않고, 범용(도메인 비특정) 관점 문구를 덧붙인 query 몇
개로 나눠 기존 WebSearchProvider.search()를 반복 호출한 뒤 결과를
URL 기준으로 합친다 - 새 Search AI/Provider를 만들지 않고 기존 Tool을
그대로 재사용한다. 단어 수가 적은(단순한) 조사는 이전과 완전히 동일하게
단일 호출만 하며, 이 경로는 예외 처리 방식까지 포함해 44단계 이전
코드와 100% 동일하게 남긴다(기존 계약/기존 테스트 보호).

46단계 - on_progress(선택적 콜백)로 "검색 N/M 시작/완료 - 결과 X건"
같은 짧은 진행 문구를 알린다. API 응답 원문/snippet 전체/URL 전체
목록은 절대 넣지 않는다(§5 - 결과 "건수"만 담는다). on_progress가
None이면(기존 호출부) 아무 것도 하지 않는다 - 기존 계약을 전혀
바꾸지 않는다(§4).
"""

from typing import Callable

from .task import Task
from .worker import Worker
from .worker_context import WorkerContext

RESEARCH_TASK_TYPE = "research"
WEB_SEARCH_TOOL_NAME = "web_search"
DEFAULT_MAX_RESULTS = 5

# 44단계 - 넓은 조사를 여러 관점으로 나누기 위한 최소 규칙 기반 설정.
# 특정 도메인(예: 게임엔진) keyword를 하드코딩하지 않는다 - 관점 이름은
# 어떤 조사 주제에도 적용 가능한 범용 표현만 쓰고, 실제 조사 "내용"은
# 항상 task.title/task.goal에서만 나온다(이 목록은 각 query 뒤에 붙는
# 접미사일 뿐이다).
_SIMPLE_QUERY_WORD_THRESHOLD = 10
_BROAD_QUERY_COUNT = 3
_MAX_QUERY_COUNT = 5
_RESEARCH_ANGLES = [
    "핵심 요구사항",
    "기존 해결책과 경쟁 사례",
    "기술적 접근 방식",
    "사용자 관점과 제약",
    "플랫폼과 운영 고려사항",
]


class ResearchWorkerError(Exception):
    """ResearchWorker가 처리할 수 없는 Task가 들어왔을 때 발생한다."""


def _plan_queries(base_query: str) -> list[str]:
    """base_query가 짧으면(단순한 조사) 44단계 이전과 완전히 동일하게
    단일 query만 돌려준다 - 단어 수 기준은 순수 구조적 판단이라 특정
    도메인에 편향되지 않는다(§3 "너무 단순한 조사라면 1~2개도 허용"의
    최소 형태 - 여기서는 1개).

    단어 수가 많으면(넓은 조사로 판단) base_query에 범용 관점 문구를
    덧붙인 query를 최대 _BROAD_QUERY_COUNT(기본 3)개까지 만든다. 모든
    query가 base_query로 시작하므로 원래 step의 title/goal 범위를
    벗어나지 않는다(§14 F). _MAX_QUERY_COUNT(5)는 항상 지킨다(§10).
    """
    if len(base_query.split()) <= _SIMPLE_QUERY_WORD_THRESHOLD:
        return [base_query]

    target = min(_BROAD_QUERY_COUNT, _MAX_QUERY_COUNT)
    queries = [base_query]
    for angle in _RESEARCH_ANGLES:
        if len(queries) >= target:
            break
        queries.append(f"{base_query} - {angle}")
    return queries[:_MAX_QUERY_COUNT]


def _emit_progress(on_progress: Callable[[str], None] | None, message: str) -> None:
    if on_progress is not None:
        on_progress(message)


def _merge_search_results(result_lists: list[list]) -> list:
    """여러 query의 검색 결과를 순서를 보존하며 하나로 합치고, 같은 URL은
    한 번만 남긴다(§7). url 필드가 없는 항목(malformed source, §13)은
    중복 여부를 판단할 수 없으므로 임의로 버리지 않고 그대로 보존한다.
    dict가 아닌 항목도 동일하게 그대로 보존한다 - 결과를 지어내지도,
    함부로 없애지도 않는다.
    """
    merged: list = []
    seen_urls: set = set()
    for results in result_lists:
        for item in results or []:
            if isinstance(item, dict):
                url = item.get("url")
                if url:
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
            merged.append(item)
    return merged


class ResearchWorker(Worker):
    """조사(research) 작업을 위해 web_search Tool을 호출하는 Worker.

    44단계 - 넓은 조사 목표는 여러 관점 query로 나눠 기존
    WebSearchProvider를 여러 번 호출한 뒤 결과를 합친다. 짧은/단순한
    조사는 이전과 완전히 동일하게 단일 호출만 한다(아래 분기 참고).
    """

    task_type = RESEARCH_TASK_TYPE

    def execute(
        self, task: Task, context: WorkerContext, on_progress: Callable[[str], None] | None = None
    ) -> object:
        if task.task_type != self.task_type:
            raise ResearchWorkerError(
                f"ResearchWorker는 task_type='{self.task_type}'만 처리할 수 있습니다: "
                f"받은 값={task.task_type}"
            )

        base_query = f"{task.title} {task.goal}".strip()
        planned_queries = _plan_queries(base_query)
        total = len(planned_queries)

        if total == 1:
            # 44단계 이전과 완전히 동일한 단일 호출 경로 - try/except로
            # 감싸지 않는다(예외를 그대로 전파한다). approved를 전달하지
            # 않는다(기본값 False) - 승인이 필요한 Tool이라면
            # ToolApprovalRequiredError가 그대로 이 아래에서 발생해
            # 전파된다. ToolApprovalRequiredError/PermissionNotFoundError/
            # ToolNotFoundError/WebSearchToolError/Provider의 일반 예외를
            # 여기서 잡아 가짜 성공 결과로 바꾸지 않는다. 46단계 -
            # _emit_progress 호출은 순수 관찰용(사이드이펙트 없음)이라
            # 이 경로의 예외 전파/결과 identity를 전혀 바꾸지 않는다.
            _emit_progress(on_progress, "검색 1/1 시작")
            search_results = context.execute_tool(
                WEB_SEARCH_TOOL_NAME,
                query=base_query,
                max_results=DEFAULT_MAX_RESULTS,
            )
            valid_count = len(search_results) if isinstance(search_results, list) else 0
            _emit_progress(on_progress, f"검색 1/1 완료 - 결과 {valid_count}건")
            _emit_progress(on_progress, f"Research 완료 - 유효 결과 {valid_count}건")
        else:
            # 44단계 §13 - 여러 query 중 일부가 실패해도(네트워크/API
            # 오류, malformed 응답 등) 전체 조사를 실패시키지 않는다 -
            # 다른 query에서 유효한 결과가 있으면 그것만으로 진행한다.
            # 실패한 query는 그대로 건너뛰고 재시도하지 않는다(무한
            # retry 금지, §10). 모든 query가 실패/빈 결과여도 예외를
            # 던지지 않고 빈 목록을 그대로 반환한다 - 그 판단(0건일 때
            # Analysis를 막는 것)은 43단계 안전장치의 몫이다(§13, 새
            # failure 상태를 만들지 않는다). KeyboardInterrupt/SystemExit는
            # Exception이 아니므로 여기서 잡히지 않고 그대로 전파된다.
            result_lists: list[list] = []
            for index, query in enumerate(planned_queries, start=1):
                _emit_progress(on_progress, f"검색 {index}/{total} 시작")
                try:
                    query_results = context.execute_tool(
                        WEB_SEARCH_TOOL_NAME,
                        query=query,
                        max_results=DEFAULT_MAX_RESULTS,
                    )
                except Exception:
                    _emit_progress(on_progress, f"검색 {index}/{total} 실패 - 건너뜀")
                    continue
                if isinstance(query_results, list):
                    result_lists.append(query_results)
                    _emit_progress(on_progress, f"검색 {index}/{total} 완료 - 결과 {len(query_results)}건")
                else:
                    _emit_progress(on_progress, f"검색 {index}/{total} 완료 - 결과 0건")
            _emit_progress(on_progress, "검색 결과 정리 중")
            search_results = _merge_search_results(result_lists)
            _emit_progress(on_progress, f"중복 제거 후 총 {len(search_results)}건")
            _emit_progress(on_progress, f"Research 완료 - 유효 결과 {len(search_results)}건")

        return {
            "task_type": task.task_type,
            "title": task.title,
            "goal": task.goal,
            "query": base_query,
            "search_results": search_results,
        }
