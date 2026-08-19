"""OpenAI Responses API의 내장 web_search Tool을 사용하는 WebSearchProvider 구현.

OpenAI client는 생성자에서 외부 주입받는다 — 이 파일 안에서 OpenAI()를
생성하거나 API Key/환경변수/.env를 직접 다루지 않는다. Brain/Developer용
Provider(openai_provider.py/openai_developer_provider.py)와는 완전히
독립적이며, 그 파일들의 previous_response_id 흐름과 섞이지 않는다.

내장 web_search Tool은 함수 호출(tool calling)과 달리 서버 쪽에서 검색을
직접 수행하므로, 이 Provider는 client.responses.create() 한 번만 호출하면
된다 — Developer Provider처럼 도구 호출 결과를 직접 실행해 되돌려주는
반복 루프가 필요 없다.

검색 결과의 title/url은 openai SDK(설치 버전 3.2.0)의
`openai.types.responses.response_output_text.AnnotationURLCitation`에서
실제로 제공하는 필드(title, url, start_index, end_index)만 사용한다.
그 타입에는 snippet 필드가 없으므로, 응답 텍스트에서 해당 인용이 걸린
구간(start_index:end_index)을 그대로 잘라 snippet으로 쓴다 — 이는 실제
응답에 존재하는 텍스트의 일부이며, AI가 지어낸 요약이 아니다.
"""

from typing import Any

from .web_search_provider import WebSearchProvider

# 이 프로젝트의 다른 Provider들과 동일한 자리표시자 모델명 표기 관례를
# 따른다. Brain/Developer Provider의 DEFAULT_MODEL을 import하지 않는다 -
# 이 Provider는 완전히 독립적으로 존재해야 한다.
DEFAULT_MODEL = "gpt-5.6-terra"

_SEARCH_INSTRUCTIONS = (
    "주어진 검색어와 관련된 최신 웹 정보를 찾아, 찾은 출처를 인용하며 "
    "답변하세요. 스스로 결론을 내리거나 분석을 덧붙이지 말고, 찾은 정보를 "
    "있는 그대로 전달하세요."
)


class OpenAIWebSearchProvider(WebSearchProvider):
    """client.responses.create()의 web_search Tool로 실제 검색을 수행한다."""

    def __init__(self, client: Any, model: str = DEFAULT_MODEL):
        self._client = client
        self._model = model

    def search(self, query: str, *, max_results: int = 5) -> list[dict]:
        response = self._client.responses.create(
            model=self._model,
            instructions=_SEARCH_INSTRUCTIONS,
            input=query,
            tools=[{"type": "web_search"}],
        )

        results = _extract_search_results(response)
        # API 자체에는 결과 개수를 제한하는 파라미터가 없으므로, 응답을
        # 전부 추출한 뒤 여기서 Python으로 자른다.
        return results[:max_results]


def _extract_search_results(response: Any) -> list[dict]:
    """response.output에서 url_citation 어노테이션만 추출해 결과 목록을 만든다.

    같은 URL이 여러 번 인용되어도 첫 등장 순서를 유지하며 한 번만 담는다.
    """
    results: list[dict] = []
    seen_urls: set[str] = set()

    for output_item in response.output:
        if getattr(output_item, "type", None) != "message":
            continue

        for content_item in output_item.content:
            if getattr(content_item, "type", None) != "output_text":
                continue

            text = content_item.text
            for annotation in content_item.annotations:
                if getattr(annotation, "type", None) != "url_citation":
                    continue
                if annotation.url in seen_urls:
                    continue
                seen_urls.add(annotation.url)

                results.append(
                    {
                        "title": annotation.title,
                        "url": annotation.url,
                        "snippet": text[annotation.start_index : annotation.end_index],
                    }
                )

    return results
