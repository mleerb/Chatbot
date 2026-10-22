import re

from app.prompts import render_prompt
from app.services.sessions import Page, Upload

PAGE_CHARS = 3000
MAX_PAGE_CHARS = 6000
OVERLAP_CHARS = 300
INLINE_TOKENS = 6000
MAX_OUTLINE = 50
PREVIEW_CHARS = 80
SNIPPET_CHARS = 120
MAX_RESULTS = 5


def estimate_tokens(text: str) -> int:
    return (len(text) + 3) // 4


def is_large(item: Upload) -> bool:
    return estimate_tokens(item.document) > INLINE_TOKENS


def split_text(text: str, size: int) -> list[str]:
    chunks, rest = [], text.strip()
    while len(rest) > size:
        cut = next((index for separator in ("\n\n", "\n", " ")
                    if (index := rest.rfind(separator, size // 2, size)) > 0), size)
        chunks.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        chunks.append(rest)
    return chunks


def text_pages(text: str) -> list[Page]:
    return [Page(str(number), chunk) for number, chunk in enumerate(split_text(text, PAGE_CHARS), 1)]


def source_pages(pages: list[tuple[int, str]]) -> list[Page]:
    result = []
    for number, text in pages:
        parts = split_text(text, MAX_PAGE_CHARS)
        result.extend(
            Page(str(number) if len(parts) == 1 else f"{number} (part {index}/{len(parts)})", part)
            for index, part in enumerate(parts, 1)
        )
    return result


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def preview(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    heading = next((line for line in lines if line.startswith("#")), lines[0] if lines else "")
    return shorten(heading.lstrip("#").strip(), PREVIEW_CHARS)


def tail(text: str) -> str:
    part = text[-OVERLAP_CHARS:]
    return part if len(text) <= OVERLAP_CHARS else part.split(maxsplit=1)[-1]


def head(text: str) -> str:
    part = text[:OVERLAP_CHARS]
    return part if len(text) <= OVERLAP_CHARS else part.rsplit(maxsplit=1)[0]


def label_for(item: Upload, number: int) -> str:
    label = item.pages[number - 1].label
    return "" if label == str(number) else label


def outline(item: Upload) -> str:
    entries = [{"number": number, "label": label_for(item, number), "preview": preview(page.text)}
               for number, page in enumerate(item.pages[:MAX_OUTLINE], 1)]
    return render_prompt(
        "outline.j2", upload_name=item.filename, file_id=item.id, page_count=len(item.pages),
        tokens=estimate_tokens(item.document), entries=entries, hidden=max(len(item.pages) - MAX_OUTLINE, 0),
    )


def read(item: Upload, number: int) -> str:
    count = len(item.pages)
    if not 1 <= number <= count:
        return f"Page {number} does not exist; {item.filename} has {count} pages. No page was read."
    return render_prompt(
        "page.j2", upload_name=item.filename, file_id=item.id, number=number, page_count=count,
        label=label_for(item, number), text=item.pages[number - 1].text,
        before=tail(item.pages[number - 2].text) if number > 1 else "",
        after=head(item.pages[number].text) if number < count else "",
    )


def snippet(text: str, needles: list[str]) -> str:
    lower = text.lower()
    start = min((index for needle in needles if (index := lower.find(needle)) >= 0), default=0)
    begin = max(start - SNIPPET_CHARS, 0)
    excerpt = shorten(text[begin:start + SNIPPET_CHARS * 2], SNIPPET_CHARS * 3)
    return ("…" if begin else "") + excerpt


def search(item: Upload, query: str) -> str:
    phrase = " ".join(query.lower().split())
    terms = [term for term in re.findall(r"\w+", phrase) if len(term) > 1]
    if not terms:
        return "Give a search query with at least one word of two or more letters."
    scored = []
    for number, page in enumerate(item.pages, 1):
        lower = page.text.lower()
        score = lower.count(phrase) * 10 + sum(lower.count(term) for term in terms)
        if score:
            scored.append((score, number))
    best = sorted(scored, key=lambda entry: (-entry[0], entry[1]))[:MAX_RESULTS]
    results = [{"number": number, "label": label_for(item, number),
                "snippet": snippet(item.pages[number - 1].text, [phrase, *terms])} for _, number in best]
    return render_prompt(
        "search.j2", upload_name=item.filename, file_id=item.id, query=query, page_count=len(item.pages),
        match_count=len(scored), results=results,
    )
