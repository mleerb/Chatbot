from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.services import pages
from app.services.sessions import Upload, sessions, sessions_lock

FILE_ID = "ID of the uploaded file; optional only when exactly one file is uploaded"


class OutlineRequest(BaseModel):
    file_id: str = Field(default="", description=FILE_ID)


class PageRequest(BaseModel):
    page: int = Field(description="Page number from 1 to the file's page count, as listed by get_outline")
    file_id: str = Field(default="", description=FILE_ID)


class SearchRequest(BaseModel):
    query: str = Field(description="Words or a short phrase to find in the file")
    file_id: str = Field(default="", description=FILE_ID)


def find_upload(token: str, file_id: str) -> Upload | str:
    with sessions_lock:
        session = sessions.get(token)
    if session is None:
        return "Session expired; no file was read."
    if not file_id and len(session.uploads) > 1:
        return "Choose a file_id; multiple files are uploaded. No file was read."
    item = session.uploads.get(file_id) if file_id else session.latest_upload
    if item is None:
        return "Uploaded file not found. Use a file_id from the uploaded file metadata. No file was read."
    if not item.pages:
        return f"{item.filename} has no readable text. No file was read."
    return item


def create_page_tools(token: str) -> list:
    @tool(
        args_schema=OutlineRequest,
        description="List the pages of an uploaded file with a short preview of each, plus its page count and size. Use first for a large file to decide which pages to read. Previews do not count as reading a page.",
    )
    def get_outline(file_id: str = "") -> str:
        item = find_upload(token, file_id)
        return item if isinstance(item, str) else pages.outline(item)

    @tool(
        args_schema=PageRequest,
        description="Read one page of an uploaded file in full, with a short overlap from the neighbouring pages for context. Report every page you read to the user.",
    )
    def read_page(page: int, file_id: str = "") -> str:
        item = find_upload(token, file_id)
        return item if isinstance(item, str) else pages.read(item, page)

    @tool(
        args_schema=SearchRequest,
        description="Keyword search in an uploaded file. Returns the best-matching page numbers with short snippets; read a page with read_page before relying on it.",
    )
    def search_in_file(query: str, file_id: str = "") -> str:
        item = find_upload(token, file_id)
        return item if isinstance(item, str) else pages.search(item, query)

    return [get_outline, read_page, search_in_file]
