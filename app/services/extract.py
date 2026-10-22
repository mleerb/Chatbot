import base64
import hashlib
import io
from pathlib import Path

from docx import Document
from PIL import Image, UnidentifiedImageError

from app.core.file_types import IMAGE_EXTENSIONS, TEXT_EXTENSIONS
from app.services import parse
from app.services.pages import source_pages, text_pages
from app.services.sessions import Page

def extract_docx(data: bytes) -> str:
    document = Document(io.BytesIO(data))
    parts = []
    for block in document.iter_inner_content():
        if hasattr(block, "rows"):
            for row in block.rows:
                parts.append(" | ".join(cell.text.strip() for cell in row.cells))
        elif block.text.strip():
            parts.append(block.text.strip())
    return "\n".join(parts).strip()


def image_context(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.thumbnail((1024, 1024))
            output = io.BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=80)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return ""
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def file_context(filename: str, data: bytes) -> tuple[str, str, str]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        try:
            text = extract_docx(data)
        except Exception:
            return "", "", "Could not extract text from this Word file."
    elif suffix in TEXT_EXTENSIONS:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return "", "", "Could not decode this text file as UTF-8."
    elif suffix in IMAGE_EXTENSIONS:
        image = image_context(data)
        if image:
            return "", image, "Image ready (requires a vision-capable model)."
        return "", "", "Could not read this image."
    else:
        return "", "", "File accepted, but this file type cannot be analyzed. It will not be executed."
    if not text.strip():
        return "", "", "File accepted, but no readable text was found."
    return text, "", "Text ready for chat."


def parse_key(filename: str, data: bytes) -> str:
    return f"{Path(filename).suffix.lower()}:{hashlib.sha256(data).hexdigest()}"


def upload_context(filename: str, data: bytes,
                   cache: dict[str, list[tuple[int, str]]] | None = None) -> tuple[str, str, str, list[Page]]:
    text, image_url, status = file_context(filename, data)
    if not data or not parse.enabled():
        return text, image_url, status, text_pages(text)
    key = parse_key(filename, data)
    parsed = cache.get(key) if cache is not None else None
    if parsed is None:
        try:
            parsed = parse.parse_file(filename, data)
        except parse.ParseError:
            return text, image_url, f"LlamaParse could not read this file. {status}", text_pages(text)
        if parsed and cache is not None:
            cache[key] = parsed
    if not parsed:
        return text, image_url, f"LlamaParse found no readable text. {status}", text_pages(text)
    pages = source_pages(parsed)
    document = "\n\n".join(page.text for page in pages)
    if image_url:
        return document, image_url, "Parsed with LlamaParse. Image ready (requires a vision-capable model).", pages
    return document, "", "Parsed with LlamaParse.", pages
