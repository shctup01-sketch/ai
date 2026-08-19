import json
import os
from pathlib import Path

from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from project_runner import EntryPointError, resolve_entry_point
from workspace_guard import WorkspaceGuard, WorkspaceSecurityError, create_project_folder

from .developer_fix_request import DeveloperFixRequest
from .developer_instructions import DEVELOPER_FIX_INSTRUCTIONS, DEVELOPER_INSTRUCTIONS
from .developer_provider import DeveloperProvider
from .developer_request import DeveloperRequest
from .developer_result import DeveloperResult
from .environment_info import collect_environment_info, format_environment_info

DEFAULT_MODEL = "gpt-5.6-terra"
MAX_TOOL_CALLS = 12
# 패키지 수정 요청은 새 프로젝트를 만드는 것보다 작업 범위가 훨씬 좁으므로
# (보통 requirements.txt 한 파일, 많아야 관련 파일 몇 개) 기존 build_project
# 한도보다 더 작은 한도를 둔다. 요청하신 "기존 한도와 같거나 더 작게"를 만족한다.
MAX_FIX_TOOL_CALLS = 6

_TOOLS = [
    {
        "type": "function",
        "name": "list_files",
        "description": "현재 프로젝트 폴더 안의 파일 목록을 확인합니다.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "read_file",
        "description": "현재 프로젝트 폴더 안의 텍스트 파일을 읽습니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "프로젝트 폴더 기준 상대 경로"},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "write_file",
        "description": "현재 프로젝트 폴더 안에 파일을 생성하거나 수정합니다.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "프로젝트 폴더 기준 상대 경로"},
                "content": {"type": "string", "description": "파일에 저장할 전체 내용"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class OpenAIDeveloperProvider(DeveloperProvider):
    """OpenAI Responses API의 도구 호출(tools) + Structured Outputs를 사용하는 Developer 구현."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model

    def build_project(self, request: DeveloperRequest) -> DeveloperResult:
        api_key = self._require_api_key()
        project_path = create_project_folder(request.project_name)
        guard = WorkspaceGuard(project_path)

        env_info = collect_environment_info()
        task_prompt = (
            f"{format_environment_info(env_info)}\n\n"
            f"프로젝트 이름: {request.project_name}\n"
            f"요구사항 요약: {request.requirements_summary}\n"
            f"기능 목록: {', '.join(request.feature_list)}\n"
            f"작업 단계: {', '.join(request.task_steps)}\n\n"
            "위 계획대로 프로젝트 파일을 작성해주세요."
        )

        result = self._run_developer_session(
            api_key=api_key,
            project_path=project_path,
            guard=guard,
            instructions=DEVELOPER_INSTRUCTIONS,
            task_prompt=task_prompt,
            max_tool_calls=MAX_TOOL_CALLS,
        )
        return self._verify_result(result, project_path, guard)

    def fix_packages(self, project_path: Path, request: DeveloperFixRequest) -> DeveloperResult:
        """패키지 설치 실패 이후, 기존 프로젝트를 최소한으로 수정하는 별도 요청.

        build_project()와 달리 새 프로젝트 폴더를 만들지 않고, 이미 존재하는
        project_path에 그대로 WorkspaceGuard를 바인딩해 기존 파일만 다룬다.
        previous_response_id로 build_project() 대화를 억지로 이어붙이지 않고
        완전히 새로운 독립 대화로 시작한다 — 원래 대화가 이미 끝난 뒤(성공
        응답을 받은 뒤) 한참 지나서 발생하는 별개의 요청이고, 실행 환경 등
        필요한 맥락은 이번 프롬프트에 전부 새로 포함하기 때문에 이어붙일
        이유가 없다.
        """
        api_key = self._require_api_key()
        guard = WorkspaceGuard(project_path)

        env_info = collect_environment_info()
        task_prompt = (
            f"{format_environment_info(env_info)}\n\n"
            f"프로젝트 이름: {request.project_name}\n"
            f"현재 실행 시작 파일(entry_point): {request.entry_point}\n\n"
            f"현재 requirements.txt 내용:\n{request.requirements_text or '(없음)'}\n\n"
            "패키지 설치(dependency installation) 단계에서 다음 오류가 발생했습니다:\n"
            f"{request.pip_stderr}\n\n"
            "위 오류를 분석해 현재 실행 환경과 호환되는 구성으로 프로젝트를 "
            "최소한으로 수정해주세요."
        )

        result = self._run_developer_session(
            api_key=api_key,
            project_path=project_path,
            guard=guard,
            instructions=DEVELOPER_FIX_INSTRUCTIONS,
            task_prompt=task_prompt,
            max_tool_calls=MAX_FIX_TOOL_CALLS,
        )
        return self._verify_result(result, project_path, guard)

    @staticmethod
    def _require_api_key() -> str:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI API Key가 설정되지 않았습니다. "
                "프로젝트 루트의 .env 파일에 OPENAI_API_KEY 값을 입력한 뒤 다시 시도해주세요."
            )
        return api_key

    def _run_developer_session(
        self,
        api_key: str,
        project_path: Path,
        guard: WorkspaceGuard,
        instructions: str,
        task_prompt: str,
        max_tool_calls: int,
    ) -> DeveloperResult:
        """도구 호출 왕복 루프 본체. build_project()/fix_packages()가 공유한다.

        previous_response_id로 대화를 이어가면서, 다음 요청의 input에는
        이전 응답 전체가 아니라 새로 생긴 function_call_output만 담는다
        (이전 응답 객체를 그대로 재전송하면 status 같은 응답 전용 필드 때문에
        BadRequestError가 발생했던 문제가 있었다 — 그 방식은 절대 복원하지 않는다).
        """
        created_files: set[str] = set()
        modified_files: set[str] = set()

        client = OpenAI(api_key=api_key)

        input_items: list = [{"role": "user", "content": task_prompt}]
        previous_response_id: str | None = None

        tool_call_count = 0
        response = None

        try:
            while True:
                call_kwargs = {
                    "model": self._model,
                    "instructions": instructions,
                    "input": input_items,
                    "tools": _TOOLS,
                    "max_tool_calls": max_tool_calls,
                    "parallel_tool_calls": False,
                    "text_format": DeveloperResult,
                }
                if previous_response_id is not None:
                    call_kwargs["previous_response_id"] = previous_response_id

                response = client.responses.parse(**call_kwargs)

                function_calls = [item for item in response.output if item.type == "function_call"]
                if not function_calls:
                    break

                function_call_outputs = []
                for call in function_calls:
                    tool_call_count += 1
                    if tool_call_count > max_tool_calls:
                        raise RuntimeError(
                            f"Developer 작업 한도({max_tool_calls}회 도구 호출)를 초과해 중단되었습니다."
                        )

                    output_text = self._execute_tool(guard, call, created_files, modified_files)
                    function_call_outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": output_text,
                        }
                    )

                previous_response_id = response.id
                input_items = function_call_outputs
        except AuthenticationError as exc:
            raise RuntimeError(
                "OpenAI API Key가 올바르지 않습니다. .env 파일의 값을 확인해주세요."
            ) from exc
        except RateLimitError as exc:
            raise RuntimeError(
                "OpenAI 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            ) from exc
        except APIConnectionError as exc:
            raise RuntimeError(
                "인터넷 연결을 확인해주세요. OpenAI 서버에 연결할 수 없습니다."
            ) from exc
        except BadRequestError as exc:
            # 진단 목적의 임시 처리: 원인 파악을 위해 예외 클래스명/상태 코드/안전한
            # 오류 메시지만 보여준다. API Key, 요청 본문, 응답 원문은 절대 포함하지 않는다.
            safe_message = getattr(exc, "message", None) or str(exc)
            raise RuntimeError(
                "Developer API 오류\n"
                f"{exc.__class__.__name__}\n"
                f"HTTP {exc.status_code}\n"
                f"{safe_message}"
            ) from exc
        except OpenAIError as exc:
            raise RuntimeError(
                "OpenAI API 호출 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요."
            ) from exc

        if response is None or response.output_parsed is None:
            raise RuntimeError("Developer의 최종 결과를 이해하지 못했습니다. 다시 시도해주세요.")

        return response.output_parsed.model_copy(
            update={
                "project_path": str(project_path),
                "created_files": sorted(created_files),
                "modified_files": sorted(modified_files),
            }
        )

    @staticmethod
    def _verify_result(result: DeveloperResult, project_path: Path, guard: WorkspaceGuard) -> DeveloperResult:
        """모델의 status="success" 자기 보고를 그대로 신뢰하지 않는다.

        "개발 완료"는 코드 파일이 생성됐다는 뜻이 아니라 실행 가능한
        프로젝트가 만들어졌다는 뜻이다. entry_point가 실제로 존재/안전한지,
        requirements.txt가 있다면 실제로 읽을 수 있는지를 프로그램이 직접
        확인하고, 확인되지 않으면 success를 failed로 전환한다.

        프로젝트 폴더 밖 접근이나 .venv 접근은 여기서 다시 검사하지 않는다 —
        list_files/read_file/write_file 도구가 WorkspaceGuard를 통해서만
        동작하므로, 그런 시도는 애초에 도구 호출 시점에 거부되어 성공할 방법이
        없다 (사후 검증이 아니라 구조적으로 불가능하다).
        """
        if result.status != "success":
            return result

        verification_errors: list[str] = []

        try:
            resolve_entry_point(project_path, result.entry_point)
        except EntryPointError as exc:
            verification_errors.append(
                f"실행 진입 파일을 확인할 수 없습니다: {result.entry_point} ({exc})"
            )

        requirements_path = project_path / "requirements.txt"
        if requirements_path.exists():
            try:
                guard.read_file("requirements.txt")
            except WorkspaceSecurityError as exc:
                verification_errors.append(f"requirements.txt를 확인할 수 없습니다: {exc}")

        if not verification_errors:
            return result

        return result.model_copy(
            update={
                "status": "failed",
                "errors": [*result.errors, *verification_errors],
            }
        )

    @staticmethod
    def _execute_tool(
        guard: WorkspaceGuard,
        call,
        created_files: set,
        modified_files: set,
    ) -> str:
        try:
            arguments = json.loads(call.arguments) if call.arguments else {}
        except json.JSONDecodeError:
            return "오류: 잘못된 도구 호출 인자입니다."

        try:
            if call.name == "list_files":
                files = guard.list_files()
                return "\n".join(files) if files else "(빈 폴더)"

            if call.name == "read_file":
                return guard.read_file(arguments.get("path", ""))

            if call.name == "write_file":
                path = arguments.get("path", "")
                existed = guard.resolve_path(path).exists()
                guard.write_file(path, arguments.get("content", ""))
                (modified_files if existed else created_files).add(path)
                return f"저장 완료: {path}"

            return f"오류: 알 수 없는 도구입니다: {call.name}"
        except WorkspaceSecurityError as exc:
            return f"거부됨: {exc}"
