import json
import re

from app.formats import make_docx, make_pdf

FILENAME = "aster-answer"
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
EMPHASIS = re.compile(r"(\*\*|__|\*|_|~~|`)(?=\S)(.+?)(?<=\S)\1")
ORDERED = re.compile(r"\d+[.)]\s+")


def plain(text: str) -> str:
    text = LINK.sub(lambda match: match[1] if match[1] == match[2] else f"{match[1]} ({match[2]})", text)
    previous = None
    while previous != text:
        previous, text = text, EMPHASIS.sub(r"\2", text)
    return text.strip()


def cells(line: str) -> list[str]:
    return [plain(cell) for cell in line.strip().strip("|").split("|")]


def table_block(lines: list[str]) -> dict | None:
    rows = [cells(line) for line in lines if not re.fullmatch(r"[\s|:-]+", line)]
    if not rows:
        return None
    width = max(len(row) for row in rows)
    return {"type": "table", "rows": [row + [""] * (width - len(row)) for row in rows]}


def markdown_blocks(content: str) -> list[dict]:
    blocks, lines, index = [], content.replace("\r\n", "\n").split("\n"), 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            code = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code.append(lines[index])
                index += 1
            if code:
                blocks.append({"type": "paragraph", "text": "\n".join(code)})
        elif stripped.startswith("|"):
            table = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table.append(lines[index])
                index += 1
            if block := table_block(table):
                blocks.append(block)
            continue
        elif match := re.match(r"#{1,6}\s+(.*)", stripped):
            blocks.append({"type": "heading", "text": plain(match[1])})
        elif match := re.match(r"[-*+]\s+(.*)", stripped):
            indent = "    " * ((len(line) - len(line.lstrip())) // 2)
            blocks.append({"type": "paragraph", "text": f"{indent}• {plain(match[1])}"})
        elif ORDERED.match(stripped):
            blocks.append({"type": "paragraph", "text": plain(stripped)})
        elif stripped and not re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            blocks.append({"type": "paragraph", "text": plain(stripped.lstrip("> "))})
        index += 1
    return blocks or [{"type": "paragraph", "text": ""}]


def export(content: str, kind: str) -> tuple[str, bytes]:
    if kind == "md":
        return f"{FILENAME}.md", content.encode()
    payload = json.dumps({"blocks": markdown_blocks(content)})
    data = make_docx(payload) if kind == "docx" else make_pdf(payload)
    return f"{FILENAME}.{kind}", data
