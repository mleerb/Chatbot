import io
import zipfile
from pathlib import Path

from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

from app.core.errors import ServiceError
from app.core.file_types import TEXT_EXTENSIONS
from app.db import repository
from app.services.conversations import ensure_active

MAX_BYTES = 20 * 1024 * 1024
MAX_TEXT = 200_000
MAX_ENTRIES = 500
MAX_ROWS = 200
MAX_COLUMNS = 30


def generated_file(session, file_id):
    with session.lock:
        ensure_active(session)
        item = session.generated.get(file_id)
        if item is None:
            raise ServiceError(404, "Generated file not found")
        if not session.guest:
            files = repository.conversation_files(session.user_id, session.conversation_id)
            if not any(row["file_id"] == file_id and row["kind"] == "generated" for row in files):
                raise ServiceError(404, "Generated file not found")
        return item


def package_entries(data):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES or sum(item.file_size for item in entries) > MAX_BYTES:
            raise ValueError("Archive exceeds preview limits")
        if any(item.flag_bits & 1 for item in entries):
            raise ValueError("Encrypted archive")
        return entries


def describe(item):
    suffix = Path(item.filename).suffix.lower()
    result = {"filename": item.filename, "kind": "unsupported", "truncated": False,
              "notice": "Preview is unavailable. Download the file to view it."}
    if len(item.data) > MAX_BYTES:
        result["notice"] = "This file exceeds the 20 MiB preview limit. Download the complete file to view it."
        return result
    try:
        if suffix in TEXT_EXTENSIONS:
            text = item.data.decode("utf-8-sig")
            result.update(kind="html" if suffix == ".html" else "text", text=text[:MAX_TEXT],
                          truncated=len(text) > MAX_TEXT, notice="")
        elif suffix == ".pdf" and item.data.startswith(b"%PDF-"):
            result.update(kind="pdf", notice="")
        elif suffix == ".png" and item.data.startswith(b"\x89PNG\r\n\x1a\n"):
            result.update(kind="image", notice="")
        elif suffix == ".zip":
            with zipfile.ZipFile(io.BytesIO(item.data)) as archive:
                entries = archive.infolist()
                result.update(kind="archive", entries=[{"name": row.filename[:500], "size": row.file_size}
                              for row in entries[:MAX_ENTRIES]], truncated=len(entries) > MAX_ENTRIES,
                              notice="Entry listing only; files are not extracted.")
        elif suffix in {".docx", ".xlsx", ".pptx"}:
            package_entries(item.data)
            if suffix == ".docx":
                document = Document(io.BytesIO(item.data))
                blocks, used = [], 0
                for block in document.iter_inner_content():
                    text = ("\n".join(" | ".join(cell.text for cell in row.cells) for row in block.rows)
                            if hasattr(block, "rows") else block.text)
                    used += len(text) + 2
                    blocks.append(text)
                    if used > MAX_TEXT:
                        break
                content = "\n\n".join(blocks)
                result.update(kind="text", text=content[:MAX_TEXT], truncated=used > MAX_TEXT,
                              notice="Extracted paragraphs and tables; original Word layout is not reproduced.")
            elif suffix == ".xlsx":
                workbook = load_workbook(io.BytesIO(item.data), read_only=True, data_only=False, keep_links=False)
                try:
                    sheets = []
                    truncated = len(workbook.worksheets) > 10
                    remaining = MAX_TEXT
                    for sheet in workbook.worksheets[:10]:
                        rows = []
                        for row in sheet.iter_rows(max_row=min(sheet.max_row or 1, MAX_ROWS),
                                                   max_col=min(sheet.max_column or 1, MAX_COLUMNS)):
                            values = []
                            for cell in row:
                                text = str(cell.value) if cell.value is not None else ""
                                value = text[:min(2000, remaining)]
                                truncated = truncated or len(value) < len(text)
                                remaining -= len(value)
                                values.append(value)
                            rows.append(values)
                            if remaining <= 0:
                                truncated = True
                                break
                        truncated = truncated or (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLUMNS
                        sheets.append({"name": sheet.title, "rows": rows})
                        if remaining <= 0:
                            break
                    result.update(kind="spreadsheet", sheets=sheets, truncated=truncated,
                                  notice="Cell contents only; formulas are displayed as text and never evaluated.")
                finally:
                    workbook.close()
            else:
                presentation = Presentation(io.BytesIO(item.data))
                slides = []
                for number, slide in enumerate(list(presentation.slides)[:30], 1):
                    text = "\n".join(shape.text for shape in slide.shapes if shape.has_text_frame)
                    slides.append({"name": f"Slide {number}", "text": text[:MAX_TEXT // 30]})
                result.update(kind="slides", slides=slides,
                              truncated=len(presentation.slides) > 30 or any(len(shape.text) > MAX_TEXT // 30
                              for slide in presentation.slides for shape in slide.shapes if shape.has_text_frame),
                              notice="Slide text only; original slide layout is not reproduced.")
    except Exception:
        result.update(kind="unsupported", notice="This file could not be previewed safely. Download it to view it.")
    return result


def preview(session, file_id):
    return describe(generated_file(session, file_id))


def binary(session, file_id):
    item = generated_file(session, file_id)
    kind = describe(item)["kind"]
    if kind not in {"pdf", "image"}:
        raise ServiceError(404, "Binary preview not available")
    return item.data, "application/pdf" if kind == "pdf" else "image/png"
