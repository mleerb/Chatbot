import os

from app.tools.create import create_file_tool
from app.tools.edit import create_edit_tool
from app.tools.pages import create_page_tools
from app.tools.search import create_search_tool


def tools_for_turn(session_id: str | None, question: str, sources: list[dict] | None) -> list:
    if session_id is None:
        return []
    tools = [create_file_tool(session_id), create_edit_tool(session_id), *create_page_tools(session_id)]
    if os.getenv("TAVILY_API_KEY", "").strip() and sources is not None:
        tools.append(create_search_tool(question, sources))
    return tools
