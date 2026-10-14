import base64
import io
from pathlib import Path

from docx import Document
from PIL import Image, UnidentifiedImageError

from app.file_types import IMAGE_EXTENSIONS, TEXT_EXTENSIONS

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
