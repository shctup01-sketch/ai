import json
import os

from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    OpenAIError,
    RateLimitError,
)

from workspace_guard import WorkspaceGuard, WorkspaceSecurityError, create_project_folder

from .developer_instructions import DEVELOPER_INSTRUCTIONS
from .developer_provider import DeveloperProvider
from .developer_request import DeveloperRequest
from .developer_result import DeveloperResult

DEFAULT_MODEL = "gpt-5.6-terra"
MAX_TOOL_CALLS = 12

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
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI API Key가 설정되지 않았습니다. "
                "프로젝트 루트의 .env 파일에 OPENAI_API_KEY 값을 입력한 뒤 다시 시도해주세요."
            )

        project_path = create_project_folder(request.project_name)
        guard = WorkspaceGuard(project_path)

        created_files: set[str] = set()
        modified_files: set[str] = set()

        client = OpenAI(api_key=api_key)

        task_prompt = (
            f"프로젝트 이름: {request.project_name}\n"
            f"요구사항 요약: {request.requirements_summary}\n"
            f"기능 목록: {', '.join(request.feature_list)}\n"
            f"작업 단계: {', '.join(request.task_steps)}\n\n"
            "위 계획대로 프로젝트 파일을 작성해주세요."
        )
        # 첫 요청의 input. 이후 요청부터는 이전 응답 전체를 다시 보내지 않고,
        # previous_response_id로 대화를 이어가면서 새로 생긴 function_call_output만 보낸다.
        input_items: list = [{"role": "user", "content": task_prompt}]
        previous_response_id: str | None = None

        tool_call_count = 0
        response = None

        try:
            while True:
                call_kwargs = {
                    "model": self._model,
                    "instructions": DEVELOPER_INSTRUCTIONS,
                    "input": input_items,
                    "tools": _TOOLS,
                    "max_tool_calls": MAX_TOOL_CALLS,
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
                    if tool_call_count > MAX_TOOL_CALLS:
                        raise RuntimeError(
                            f"Developer 작업 한도({MAX_TOOL_CALLS}회 도구 호출)를 초과해 중단되었습니다."
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
