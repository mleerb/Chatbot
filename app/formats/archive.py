import io
import zipfile
from pathlib import Path

from app.core.file_types import TEXT_EXTENSIONS
from app.formats.blocks import structured_content


def make_zip(content: str) -> bytes:
    entries = structured_content(content, "entries")
    if not entries:
        raise ValueError("Provide at least one entry.")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str) or not isinstance(entry.get("content"), str):
                raise ValueError("Each ZIP entry needs a name and text content.")
            name = entry["name"]
            if (not name or "\\" in name or "\x00" in name or ":" in name or
                    Path(name).is_absolute() or any(part in {"", ".", ".."} for part in name.split("/")) or
                    Path(name).suffix.lower() not in TEXT_EXTENSIONS):
                raise ValueError("ZIP entries must use safe relative text filenames.")
            if name in archive.namelist():
                raise ValueError("ZIP entry names must be unique.")
            archive.writestr(name, entry["content"].encode("utf-8"))
    return output.getvalue()
