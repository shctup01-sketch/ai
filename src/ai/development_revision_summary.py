"""수정 전/후 DeveloperResult를 비교해 사람이 읽기 쉬운 변경 요약을 만든다.

39단계 - 새 AI 호출을 추가하지 않는다(§7, 크레딧 절약) - 이미 있는
DeveloperResult.modified_files(실제 write_file 호출 여부를 프로그램이
직접 기록한 값, LLM 자기 보고가 아니다 - openai_developer_provider.py
_execute_tool 참고)와, revision 시작 전/후에 안전하게 얻은 파일 목록
(WorkspaceGuard.list_files() 재사용, 새 Git 의존성 없음)의 차이만으로
규칙 기반 요약을 만든다. 없는 diff 정보를 지어내지 않는다 - 파일 목록
비교가 실패했으면(before_files/after_files 중 하나라도 None) added_files/
removed_files는 빈 목록으로 두고 warnings에 그 사실만 정직하게 남긴다
(§12, 실패해도 revision 자체를 실패로 만들지 않는다).
"""

from pydantic import BaseModel


class DevelopmentRevisionSummary(BaseModel):
    requested_change: str
    changed_files: list[str]
    added_files: list[str]
    removed_files: list[str]
    summary: str
    warnings: list[str]


def build_revision_summary(
    requested_change: str,
    new_dev_result_modified_files: list[str],
    before_files: list[str] | None,
    after_files: list[str] | None,
) -> DevelopmentRevisionSummary:
    """규칙 기반 요약(새 AI 호출 없음, §7/§8 - "100% 반영" 같은 확정
    표현을 쓰지 않는다).
    """
    changed_files = sorted(set(new_dev_result_modified_files))
    warnings: list[str] = []

    if before_files is None or after_files is None:
        added_files: list[str] = []
        removed_files: list[str] = []
        unchanged_count: int | None = None
        warnings.append("파일 변경 목록을 확인하지 못했습니다.")
    else:
        added_files = sorted(set(after_files) - set(before_files))
        removed_files = sorted(set(before_files) - set(after_files))
        touched = set(changed_files) | set(added_files)
        unchanged_count = len([name for name in after_files if name not in touched])

    summary_parts = []
    if changed_files:
        summary_parts.append(f"{len(changed_files)}개 파일 수정")
    if added_files:
        summary_parts.append(f"{len(added_files)}개 파일 추가")
    if removed_files:
        summary_parts.append(f"{len(removed_files)}개 파일 삭제")
    if unchanged_count is not None:
        summary_parts.append(f"{unchanged_count}개 파일 유지")

    if summary_parts:
        summary_text = "요청에 따라 다음 변경이 수행되었습니다: " + ", ".join(summary_parts)
    else:
        summary_text = "요청에 따라 변경을 시도했지만 감지된 파일 변경이 없습니다."

    return DevelopmentRevisionSummary(
        requested_change=requested_change,
        changed_files=changed_files,
        added_files=added_files,
        removed_files=removed_files,
        summary=summary_text,
        warnings=warnings,
    )
