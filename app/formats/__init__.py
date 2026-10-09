from app.formats.archive import make_zip
from app.formats.pdf import make_pdf
from app.formats.sheet import make_xlsx
from app.formats.slides import make_pptx
from app.formats.word import make_docx

GENERATORS = {
    ".docx": make_docx,
    ".pdf": make_pdf,
    ".xlsx": make_xlsx,
    ".pptx": make_pptx,
    ".zip": make_zip,
}
