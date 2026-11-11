import logging
import re

import numpy as np

from app.prompts import render_prompt
from app.services import embed, storage
from app.services.sessions import Page, Upload

PAGE_CHARS = 3000
MAX_PAGE_CHARS = 6000
OVERLAP_CHARS = 300
INLINE_TOKENS = 6000
MAX_OUTLINE = 50
PREVIEW_CHARS = 80
SNIPPET_CHARS = 120
MAX_RESULTS = 5
RRF_K = 60
CANDIDATES = 50
logger = logging.getLogger(__name__)


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


def keyword_ranking(entries, phrase: str, terms: list[str]):
    scored = []
    for index, (_, _, page) in enumerate(entries):
        lower = page.text.lower()
        score = lower.count(phrase) * 10 + sum(lower.count(term) for term in terms)
        if score:
            scored.append((score, index))
    return [index for _, index in sorted(scored, key=lambda row: (-row[0], row[1]))]


def fuse(rankings: list[list[int]]) -> list[int]:
    scores = {}
    for ranking in rankings:
        for rank, index in enumerate(ranking[:CANDIDATES], 1):
            scores[index] = scores.get(index, 0) + 1 / (RRF_K + rank)
    return sorted(scores, key=lambda index: (-scores[index], index))


def ranked(items: list[Upload], query: str, session=None):
    phrase = " ".join(query.lower().split())
    terms = [term for term in re.findall(r"\w+", phrase) if len(term) > 1]
    entries = [(item, number, page) for item in items for number, page in enumerate(item.pages, 1)]
    keywords = keyword_ranking(entries, phrase, terms)
    semantic = []
    embedded_files = set()
    reason = "embeddings disabled or provider key missing"
    if session is not None and embed.available():
        config = embed.settings()
        for item in items:
            if is_large(item):
                changed = embed.prepare(item)
                if changed or item.embeddings_dirty:
                    try:
                        storage.save_embeddings(session, item)
                        item.embeddings_dirty = False
                    except Exception:
                        logger.warning("Could not persist file embeddings; will retry on a later search")
        vectors, indices = [], []
        for index, (item, number, _page) in enumerate(entries):
            if number == 1:
                decoded = embed.unpack(item.embeddings, config)
                if decoded is not None and decoded[0] != [embed.text_hash(part.text) for part in item.pages]:
                    decoded = None
            if decoded is not None:
                vectors.append(decoded[1][number - 1])
                indices.append(index)
                embedded_files.add(item.id)
        reason = "file embeddings unavailable"
        if vectors:
            try:
                vector = embed.query_vector(session, query, config)
                similarities = embed.cosine(np.asarray(vectors), vector)
                order = np.argsort(-similarities, kind="stable")[:CANDIDATES]
                semantic = [indices[int(index)] for index in order]
                reason = ""
            except Exception:
                reason = "query embedding failed"
                logger.warning("Query embedding unavailable; using keyword search")
    ranking = fuse([keywords, semantic]) if semantic else keywords
    best = ranking[:MAX_RESULTS]
    results = []
    for index in best:
        item, number, page = entries[index]
        results.append({"number": number, "label": label_for(item, number), "filename": item.filename,
                        "file_id": item.id, "snippet": snippet(page.text, [phrase, *terms]),
                        "method": "meaning + keywords" if index in semantic and index in keywords[:CANDIDATES]
                        else "meaning" if index in semantic else "keywords"})
    partial = bool(semantic) and len(embedded_files) < len(items)
    mode = "Hybrid search" if semantic else "Keyword search"
    fallback = ("Some files have no compatible embeddings; those files use keywords only." if partial else
                f"Keyword-only fallback: {reason}." if not semantic else "")
    return {"query": query, "page_count": len(entries), "match_count": len(set(keywords) | set(semantic)),
            "results": results, "mode": mode, "fallback": fallback}


def search_many(items: list[Upload], query: str, session=None) -> str:
    if not any(len(term) > 1 for term in re.findall(r"\w+", query)):
        return "Give a search query with at least one word of two or more letters."
    return render_prompt("search.j2", **ranked(items, query, session))


def search(item: Upload, query: str) -> str:
    return search_many([item], query)
