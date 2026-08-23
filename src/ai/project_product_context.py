"""프로젝트의 승인된 장기 제품 방향(57단계 - "Project Product Context").

실제 GameBlock 장기 프로젝트에서 확인된 문제: Analysis가 "GameBlock
테스트 창의 실행 증거는 인정함. 그러나... 승인된 구조의 구체적인 명세가
제공되지 않아 현재 기반이 승인 구조와 일치하는지 단정할 수 없음"이라고
판단했다. 코드로 직접 확인한 원인은, ChiefBrainPlan에는 objective(자유
텍스트 한 줄)만 있고, Analysis/Development에 실제로 전달되는
ExecutionContext/AnalysisExecutor는 depends_on으로 연결된 "직전 단계
결과"만 보며 프로젝트 전체의 장기 제품 기준을 전혀 받지 않는다는 점이다
(chief_brain_orchestrator.py._build_execution_context, analysis_executor.py.
_build_request 직접 확인, §2).

이 모델은 그 장기 기준을 짧게 구조화해서 담는다 - 매번 원본 대화
전체를 다시 넣지 않는다(§4 토큰 낭비 금지). 8개 필드 모두 선택적이고
기본값이 빈 문자열이다 - 없는 내용을 지어내지 않는다. 필드 이름은
57단계 지시에 나온 항목(비전/핵심 사용자/핵심 사용 방식/고정 UX
원칙/핵심 시스템/플랫폼 목표/현재 범위/금지·비목표)을 그대로 옮긴
것일 뿐, GameBlock 전용 내용이 아니다 - 값은 비어 있는 것이 정상이고,
어떤 프로젝트든 이 8개 항목으로 자신의 장기 기준을 채울 수 있다(§1
"GameBlock 전용 시스템을 만들지 않는다").

이 값은 "무엇을 만들기로 했는가"라는 판단 기준이다 - "무엇을 실제로
만들었는가"라는 증거(DevelopmentEvidenceSnapshot, 54단계)와는 다른
개념이다. 이 파일도, 이 값을 사용하는 곳(analysis_executor.py,
openai_research_reviewer_provider.py, checkpoint_context.py)도 이 값을
구현 증거로 취급하지 않는다(§4).
"""

from pydantic import BaseModel


class ProjectProductContext(BaseModel):
    """프로젝트의 승인된 장기 제품 방향. 8개 필드 모두 짧은 한 줄 요약을
    담기 위한 것이지, 원본 대화나 문서 전체를 담는 자리가 아니다."""

    vision: str = ""
    core_users: str = ""
    core_usage: str = ""
    fixed_ux_principles: str = ""
    core_systems: str = ""
    platform_goals: str = ""
    current_scope: str = ""
    prohibitions_non_goals: str = ""


_FIELD_LABELS: tuple[tuple[str, str], ...] = (
    ("vision", "비전"),
    ("core_users", "핵심 사용자"),
    ("core_usage", "핵심 사용 방식"),
    ("fixed_ux_principles", "고정 UX 원칙"),
    ("core_systems", "핵심 시스템"),
    ("platform_goals", "플랫폼 목표"),
    ("current_scope", "현재 범위"),
    ("prohibitions_non_goals", "금지/비목표"),
)


def has_product_context_content(context: "ProjectProductContext | None") -> bool:
    """8개 필드 중 하나라도 실제로 채워져 있는지만 확인한다(존재하지
    않는 내용을 있다고 판단하지 않는다)."""
    if context is None:
        return False
    return any(getattr(context, field).strip() for field, _ in _FIELD_LABELS)


def describe_product_context(context: "ProjectProductContext | None") -> str:
    """AI 프롬프트/화면에 그대로 넣을 수 있는 짧은 텍스트로 만든다.

    비어 있는 필드는 줄 자체를 만들지 않는다(없는 내용을 "없음"으로
    나열해 프롬프트 길이만 늘리지 않는다, §4/§7). context가 None이거나
    채워진 필드가 하나도 없으면 빈 문자열을 돌려준다 - 호출자가 이를
    보고 "아직 제품 기준이 설정되지 않았다"고 판단할 수 있다.
    """
    if not has_product_context_content(context):
        return ""
    lines = [f"{label}: {getattr(context, field).strip()}" for field, label in _FIELD_LABELS if getattr(context, field).strip()]
    return "\n".join(lines)
