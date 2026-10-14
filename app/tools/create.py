from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.sessions import sessions, sessions_lock
from app.file_types import TEXT_EXTENSIONS
from app.formats import GENERATORS


class CreatedFile(BaseModel):
    filename: str = Field(description="A simple filename with a supported text extension, .docx, .pdf, .xlsx, .pptx or .zip")
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
        description="Create a real downloadable text, .docx, .pdf, .xlsx, .pptx or .zip file. For .docx/.pdf use plain text or JSON {'blocks':[{'type':'heading'|'paragraph','text':'...'}, {'type':'table','rows':[['A','B']]}]}. For .xlsx use {'sheets':[{'name':'Sheet1','rows':[['A',1]]}]}; .pptx use {'slides':[{'title':'Title','body':'Text'}]}; .zip use {'entries':[{'name':'notes.txt','content':'Text'}]}. Do not generate images or executables.",
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
        session.generated_filename = name
        session.generated_bytes = data
        return f"Created downloadable file: {name}"

    return create_text_file
