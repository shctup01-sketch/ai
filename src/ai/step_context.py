"""이전 step 결과를 다음 step에 안전하게 전달하기 위한 Result Context 모델.

BrainTaskStep.goal은 Chief Brain이 만든 원본 계획 텍스트다 - 이 파일의
어떤 값도 그 원본을 수정하는 데 쓰이지 않는다(Orchestrator가 원본 step
객체를 절대 바꾸지 않는다는 기존 원칙과 동일하게, 여기서도 새 텍스트를
"만들어서 별도로 전달"할 뿐 step.goal 자체는 건드리지 않는다). 이
파일은 "이미 완료된 선행 step의 결과"만 표현하는 순수 데이터 모델이자
직렬화 함수다 - API Key/.env/os.environ/파일 시스템은 전혀 다루지
않는다.

특정 task_type(research/development 등)을 모델 자체에 하드코딩하지
않는다 - 어떤 task_type의 결과든 같은 구조(StepContext)로 담을 수
있어야 향후 research->analysis, development->review, review->publish,
document->email 같은 새 조합에도 이 파일을 고치지 않고 재사용할 수
있다. 직렬화 함수만 "ResearchWorker가 반환하는 모양(dict에
search_results 키가 있는 경우)"을 사람이 읽기 좋게 포맷하는 예외적인
경로를 하나 갖고, 그 모양이 아닌 결과는 task_type과 무관하게 동일한
일반 경로(그대로 문자열화)로 처리한다.
"""

from pydantic import BaseModel

# dependency 하나를 직렬화한 텍스트의 최대 길이. 검색 결과가 아주 커질
# 수 있으므로 Development 요청이 무제한으로 비대해지지 않도록 막는다.
DEFAULT_MAX_LENGTH_PER_DEPENDENCY = 8000

_TRUNCATION_NOTICE = "\n[이전 단계 결과 일부가 길이 제한으로 생략됨]"


class StepContext(BaseModel):
    """완료된 선행 step 하나의 결과."""

    step_id: str
    task_type: str
    result: object


class ExecutionContext(BaseModel):
    """현재 step이 참조할 수 있는 선행 step 결과들의 모음.

    dependencies는 step.depends_on에 적힌 순서를 그대로 유지한다.
    """

    dependencies: list[StepContext]


def _format_search_results(search_results: list) -> str:
    lines = []
    for idx, item in enumerate(search_results, start=1):
        if not isinstance(item, dict):
            lines.append(f"{idx}. {item}")
            continue
        title = item.get("title", "")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        lines.append(f"{idx}. {title}\n   {url}\n   {snippet}")
    return "\n".join(lines) if lines else "(검색 결과 없음)"


def _format_step_result(step: StepContext) -> str:
    result = step.result
    if isinstance(result, dict) and "search_results" in result:
        # ResearchWorker(research_worker.py)가 반환하는 모양을 사람이
        # 읽기 좋은 형태로 풀어낸다. task_type 문자열 자체를 검사하지
        # 않는다 - 결과의 "모양"만 본다.
        query = result.get("query", "")
        body = f"검색어: {query}\n검색 결과:\n{_format_search_results(result.get('search_results') or [])}"
    else:
        # 알려진 모양이 아니면(development 결과 등) 일반적인 방식으로
        # 그대로 문자열화한다 - 특정 task_type을 더 추가하지 않아도
        # 항상 안전하게 동작한다.
        body = str(result)

    return f"[이전 단계({step.step_id}) 결과]\n{body}"


def serialize_step_context(step: StepContext, max_length: int = DEFAULT_MAX_LENGTH_PER_DEPENDENCY) -> str:
    """dependency 하나를 사람이 읽을 수 있는 텍스트로 직렬화한다.

    합리적인 길이 상한을 넘으면 조용히 자르지 않고, 잘렸다는 사실을
    텍스트 끝에 명시적으로 남긴다.
    """
    text = _format_step_result(step)
    if len(text) > max_length:
        text = text[:max_length] + _TRUNCATION_NOTICE
    return text


def serialize_execution_context(
    context: ExecutionContext, max_length_per_dependency: int = DEFAULT_MAX_LENGTH_PER_DEPENDENCY
) -> str:
    """ExecutionContext 전체를 dependency 순서대로 이어붙인 텍스트로 만든다.

    dependencies가 비어 있으면 빈 문자열을 반환한다(호출자가 이를 보고
    "참고할 이전 결과가 없다"고 판단할 수 있다).
    """
    if not context.dependencies:
        return ""
    return "\n\n".join(
        serialize_step_context(step, max_length=max_length_per_dependency) for step in context.dependencies
    )
