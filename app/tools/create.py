from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.core.file_types import TEXT_EXTENSIONS
from app.formats import GENERATORS
from app.prompts import render_prompt
from app.services import storage
from app.services.sessions import Download, sessions, sessions_lock


class CreatedFile(BaseModel):
    filename: str = Field(description="A simple filename preserving the requested extension: "
                          + ", ".join(sorted(TEXT_EXTENSIONS)) + ", .docx, .pdf, .xlsx, .pptx or .zip")
    content: str = Field(description="Text for text files; plain text or JSON blocks for .docx/.pdf; JSON sheets/slides/entries for .xlsx/.pptx/.zip")


def validate_file(filename: str, content: str) -> tuple[str, bytes]:
    if (not filename or filename in {".", ".."} or "/" in filename or "\\" in filename
            or "\x00" in filename or Path(filename).suffix.lower() not in TEXT_EXTENSIONS | GENERATORS.keys()):
        raise ValueError("Unsupported format. Use a simple text, .docx, .pdf, .xlsx, .pptx or .zip filename.")
    extension = Path(filename).suffix.lower()
    try:
        data = GENERATORS[extension](content) if extension in GENERATORS else content.encode("utf-8")
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise ValueError(f"Invalid {extension} content: {exc}") from exc
    return filename, data


def create_file_tool(token: str):
    @tool(
        args_schema=CreatedFile,
        description=render_prompt("create.j2"),
    )
    def create_text_file(filename: str, content: str) -> str:
        try:
            name, data = validate_file(filename, content)
        except ValueError as exc:
            return str(exc)
        with sessions_lock:
            session = sessions.get(token)
        if session is None:
            return "Session expired; file was not created."
        item = Download(name, data)
        try:
            storage.save_generated(session, item)
        except Exception:
            return "Could not save the file; it was not created."
        session.generated[item.id] = item
        return f"Created downloadable file: {name} (file_id={item.id})"

    return create_text_file
