import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.formats.blocks import document_blocks, table_rows


def make_pdf(content: str) -> bytes:
    styles = getSampleStyleSheet()
    story = []
    for block in document_blocks(content):
        if not isinstance(block, dict):
            raise ValueError("Document blocks must be objects.")
        kind = block.get("type")
        if kind in {"heading", "paragraph"} and isinstance(block.get("text"), str):
            style = styles["Heading1"] if kind == "heading" else styles["Normal"]
            story.extend([Paragraph(escape(block["text"]).replace("\n", "<br/>"), style), Spacer(1, 8)])
        elif kind == "table":
            rows = table_rows(block)
            table = Table([[Paragraph(escape(str(cell)), styles["Normal"]) for cell in row] for row in rows])
            table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
            story.extend([table, Spacer(1, 8)])
        else:
            raise ValueError("Unsupported document block.")
    output = io.BytesIO()
    SimpleDocTemplate(output).build(story)
    return output.getvalue()
