"""PersistentProjectState를 JSON 파일로 저장/조회하는 저장소(41단계).

MainWindow는 이 파일을 통해서만 디스크에 접근한다 - JSON dump/load를
MainWindow 안에 직접 길게 구현하지 않는다(§10). 저장 위치는 Studio
자신의 전용 디렉터리(get_project_state_root())이지, Developer 프로젝트가
생성되는 workspace 폴더(§6)가 아니다 - 그 폴더는 WorkspaceGuard가
지키는 프로젝트 소스 전용 영역이라 Studio 상태 파일을 섞지 않는다.
이 파일도 그 보호 장치를 우회하거나 흉내내지 않는다 - 아예 다른
디렉터리를 쓸 뿐이다.

result_type 태그(§9, "저장 후 다시 불러왔을 때 원래 타입 구조로
복구되어야 한다"): OrchestrationStepResult.result는 object 타입으로
열려 있어(analysis/development/screen_observation/research가 각각
ResearchReviewResult/DeveloperResult/ScreenObservationResult/plain dict를
담는다) model_dump(mode="json")만으로는 다시 읽을 때 어떤 pydantic
모델로 복구해야 하는지 알 수 없다(실측 확인 - object 타입 필드는
읽어들이면 그냥 dict로 남는다). 그래서 저장 시점에만 실제 파이썬
타입을 보고 태그 하나를 함께 적어두고, 불러올 때 그 태그로 정확히
같은 모델 클래스에 model_validate()한다 - 새로운 직렬화 프로토콜이
아니라 이미 있는 각 모델의 model_dump/model_validate를 그대로 쓴다.
"""

import json
import os
from pathlib import Path

from pydantic import BaseModel

from .developer_result import DeveloperResult
from .development_evidence_snapshot import DevelopmentEvidenceSnapshot
from .project_state import SCHEMA_VERSION, PersistentProjectState
from .research_review_result import ResearchReviewResult
from .screen_observation_result import ScreenObservationResult

# object 타입 result 필드에 담길 수 있는, 이미 존재하는 pydantic 모델만
# 등록한다(§9 - 새 모델을 만들지 않는다). research task의 result는 원래도
# 순수 dict(research_worker.py 참고)라 여기 등록할 모델이 없다 - "raw"
# 태그로 그대로 왕복시킨다.
#
# 54단계 - DevelopmentEvidenceSnapshot(DeveloperResult를 상속, 실행
# 검증/화면 검수/수정 이력 증거를 선택적으로 담는다)도 여기 등록해야
# 저장 후 다시 불러왔을 때 순수 dict가 아니라 원래 타입으로 복구된다
# (§5 - 이 등록이 없으면 evidence가 재시작 후 사라지는 문제 자체가
# 그대로 남는다). type(result).__name__이 "DeveloperResult"가 아니라
# "DevelopmentEvidenceSnapshot"으로 저장되므로 별도 태그가 필요하다.
_RESULT_MODEL_REGISTRY: dict[str, type[BaseModel]] = {
    "ResearchReviewResult": ResearchReviewResult,
    "DeveloperResult": DeveloperResult,
    "DevelopmentEvidenceSnapshot": DevelopmentEvidenceSnapshot,
    "ScreenObservationResult": ScreenObservationResult,
}


class ProjectStateError(Exception):
    """저장/불러오기가 안전하게 실패했을 때 발생한다(§18 - 앱을 죽이지 않는다).

    JSON 손상/파일 없음/지원하지 않는 schema_version/필수 필드 누락/
    직렬화 실패/쓰기 권한 실패를 이 하나의 예외로 감싸, 호출자(MainWindow)가
    항상 같은 방식으로 안전하게 처리할 수 있게 한다.
    """


def get_project_state_root() -> Path:
    """<프로젝트 루트>/studio_state 를 반환하고, 없으면 만든다.

    Developer 프로젝트 소스가 생성되는 workspace 폴더와는 완전히 다른,
    Studio 자신의 상태 저장 전용 디렉터리다(§6).
    """
    src_dir = Path(__file__).resolve().parent.parent
    project_root = src_dir.parent
    state_root = project_root / "studio_state"
    state_root.mkdir(exist_ok=True)
    return state_root


def _result_type_tag(result: object | None) -> str | None:
    if result is None:
        return None
    if isinstance(result, BaseModel):
        return type(result).__name__
    return "raw"


def _reconstruct_result(result_type: str | None, raw_result):
    if raw_result is None or result_type is None:
        return raw_result
    if result_type == "raw":
        return raw_result
    model_cls = _RESULT_MODEL_REGISTRY.get(result_type)
    if model_cls is None:
        # 알 수 없는 타입 태그(예: 이후 버전에서 추가된 모델)를 만나도
        # 전체 로드를 막지 않는다 - 원본 dict라도 그대로 보존해 돌려준다.
        return raw_result
    return model_cls.model_validate(raw_result)


def _state_to_json_dict(state: PersistentProjectState) -> dict:
    data = state.model_dump(mode="json")
    for entry_dict, entry_model in zip(data["completed_steps"], state.completed_steps):
        entry_dict["result_type"] = _result_type_tag(entry_model.result)
    return data


def _json_dict_to_state(data: dict) -> PersistentProjectState:
    data = dict(data)
    completed_steps = []
    for entry_dict in data.get("completed_steps", []):
        entry_dict = dict(entry_dict)
        result_type = entry_dict.pop("result_type", None)
        entry_dict["result"] = _reconstruct_result(result_type, entry_dict.get("result"))
        completed_steps.append(entry_dict)
    data["completed_steps"] = completed_steps
    return PersistentProjectState.model_validate(data)


class ProjectStateStore:
    """create/save/load/list_projects만 담당한다(§10) - 삭제/복제/검색/
    클라우드 동기화 등 이번 단계에 필요 없는 기능은 만들지 않는다.
    """

    def __init__(self, root: Path | None = None):
        self._root = root or get_project_state_root()

    def _path_for(self, project_id: str) -> Path:
        return self._root / f"{project_id}.json"

    def save(self, state: PersistentProjectState) -> None:
        """원자적 저장(§7) - 임시 파일에 먼저 쓰고 os.replace()로 최종
        경로에 원자적으로 교체한다. 쓰다가 프로그램이 죽어도 기존 파일
        (또는 파일 없음) 상태가 그대로 유지될 뿐, 반쯤 써진 JSON이
        최종 경로에 남지 않는다.
        """
        target_path = self._path_for(state.project_id)

        try:
            payload = json.dumps(_state_to_json_dict(state), ensure_ascii=False, indent=2)
        except Exception as exc:
            raise ProjectStateError(f"프로젝트 상태를 직렬화하지 못했습니다: {exc}") from exc

        tmp_path = target_path.with_suffix(".json.tmp")
        try:
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, target_path)
        except OSError as exc:
            raise ProjectStateError(f"프로젝트 상태를 저장하지 못했습니다: {exc}") from exc
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def load(self, project_id: str) -> PersistentProjectState:
        path = self._path_for(project_id)
        if not path.exists():
            raise ProjectStateError(f"저장된 프로젝트를 찾을 수 없습니다: {project_id}")

        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProjectStateError(f"프로젝트 상태 파일을 읽지 못했습니다: {exc}") from exc

        try:
            raw = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ProjectStateError(f"프로젝트 상태 파일이 손상되었습니다: {exc}") from exc

        schema_version = raw.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ProjectStateError(
                f"지원하지 않는 저장 형식입니다(schema_version={schema_version!r}). "
                f"현재 Studio가 지원하는 버전: {SCHEMA_VERSION}"
            )

        try:
            return _json_dict_to_state(raw)
        except Exception as exc:
            raise ProjectStateError(f"프로젝트 상태 파일 형식이 올바르지 않습니다: {exc}") from exc

    def list_projects(self) -> list[PersistentProjectState]:
        """저장된 모든 프로젝트를 최신 수정 순으로 돌려준다.

        손상되었거나 지원하지 않는 schema_version인 파일 하나가 있어도
        전체 목록 조회를 막지 않는다(§18) - 그 파일만 조용히 건너뛴다.
        """
        states: list[PersistentProjectState] = []
        for path in sorted(self._root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if raw.get("schema_version") != SCHEMA_VERSION:
                    continue
                states.append(_json_dict_to_state(raw))
            except Exception:
                continue
        return sorted(states, key=lambda state: state.updated_at, reverse=True)
