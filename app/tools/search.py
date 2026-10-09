import os
from urllib.parse import urlsplit

import httpx
from langchain_core.tools import tool

SEARCH_URL = "https://api.tavily.com/search"


def search_web(question: str) -> list[dict[str, str]]:
    key = os.getenv("TAVILY_API_KEY", "").strip()
    if not key:
        return []
    with httpx.Client(timeout=12) as client:
        response = client.post(
            SEARCH_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={"query": question[:500], "search_depth": "basic", "max_results": 5,
                  "include_answer": False, "include_raw_content": False, "include_images": False},
        )
        response.raise_for_status()
        results = response.json().get("results", [])
    sources = []
    for item in results[:5]:
        url = item.get("url", "")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        sources.append({"title": str(item.get("title") or url)[:200],
                        "url": url, "content": str(item.get("content") or "")[:1600]})
    return sources


def create_search_tool(question: str, sources: list[dict[str, str]]):
    @tool(description="Search the internet for current, external evidence related to the user's question. Only the user's current question is sent to Tavily, never uploaded file content. Use when the question needs current facts, external verification or sources; do not use for private file-only questions.")
    def search_current_question() -> str:
        try:
            results = search_web(question)
        except (httpx.HTTPError, ValueError):
            return "Web search failed. Do not claim to have found web evidence."
        sources.extend(results)
        if not results:
            return "No web results found. Do not cite web evidence."
        return "\n\n".join(
            f"[{index}] {source['title']}\n{source['url']}\n{source['content']}"
            for index, source in enumerate(results, start=1)
        )

    return search_current_question
