"""Tool 실행 위험도와 승인 정책을 나타내는 데이터.

PermissionLevel은 특정 Tool 이름을 알지 못한다 — SAFE/CAUTION/DANGEROUS는
"어떤 종류의 행동인가"에 대한 일반적인 분류일 뿐, 어떤 실제 Tool이 어느
단계인지는 이 파일이 아니라 각 Tool 정책(ToolPermission)을 등록하는
쪽에서 결정한다.
"""

from enum import StrEnum

from pydantic import BaseModel


class PermissionLevel(StrEnum):
    """Tool 행동의 일반적인 위험 분류.

    SAFE      = 읽기/조회 중심이며 시스템 변경이 없는 작업
    CAUTION   = 파일 생성/수정 등 로컬 상태를 변경할 수 있는 작업
    DANGEROUS = 외부 발송, 게시, 삭제, 결제, 로그인, 프로그램 설치,
                시스템 명령 등 사용자에게 실제 영향을 주는 작업
    """

    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"


class ToolPermission(BaseModel):
    """하나의 Tool에 대한 권한 정책.

    level(위험도)과 requires_approval(승인 필요 여부)은 의도적으로 분리된
    별도 필드다. level이 DANGEROUS라고 해서 requires_approval이 자동으로
    True가 되지 않는다 — 이 판단은 항상 정책을 등록하는 쪽의 책임이며,
    PermissionManager는 저장된 값을 그대로 돌려줄 뿐 스스로 유추하지 않는다.
    """

    tool_name: str
    level: PermissionLevel
    requires_approval: bool
    reason: str
