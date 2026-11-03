import hashlib
import json
import re
import threading
from uuid import uuid4

from app.core.errors import ServiceError
from app.db import repository

MARKER = re.compile(r"\[([DW][1-9][0-9]*)\]")


class Evidence:
    def __init__(self, web=None):
        self.documents = []
        self.web = web if web is not None else []
        self.lock = threading.Lock()

    def read(self, item, number, page):
        revision_id = item.edits[-1].id if item.edits else item.id
        revision = hashlib.sha256(json.dumps(
            [revision_id, item.document, [(part.label, part.text) for part in item.pages]],
            ensure_ascii=False, separators=(",", ":"),
        ).encode()).hexdigest()
        location = (f"Page {page.label}" if item.status.startswith("Parsed with LlamaParse") and not item.edits
                    else f"Section {number}")
        with self.lock:
            existing = next((source for source in self.documents
                             if (source["file_id"], source["revision"], source["location"]) ==
                             (item.id, revision, location)), None)
            if existing is not None:
                return existing
            source = {
                "kind": "document", "id": uuid4().hex, "marker": f"D{len(self.documents) + 1}",
                "title": item.filename, "file_id": item.id, "revision_id": revision_id,
                "revision": revision, "version": f"Edited v{len(item.edits)}" if item.edits else "Original",
                "location": location, "text": page.text,
            }
            self.documents.append(source)
            return source

    def sources(self):
        with self.lock:
            return [*self.documents, *web_sources(self.web)]


def web_sources(items):
    result = []
    seen = set()
    for item in items:
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        result.append({"kind": "web", "marker": f"W{len(result) + 1}",
                       "title": item["title"], "url": item["url"]})
    return result


def current(token):
    from app.services.sessions import sessions, sessions_lock

    with sessions_lock:
        session = sessions.get(token)
    return session.evidence if session is not None else None


def clean(text, evidence):
    allowed = {source["marker"] for source in evidence.sources()} if evidence else set()
    output = []
    index = 0
    while index < len(text):
        if text[index] != "[":
            output.append(text[index])
            index += 1
            continue
        rest = text[index:]
        if len(rest) == 1:
            break
        if rest[1] not in "DW" or len(rest) > 2 and rest[2] not in "0123456789]":
            output.append("[")
            index += 1
            continue
        end = rest.find("]")
        newline = rest.find("\n")
        if end < 0 or 0 <= newline < end:
            if newline >= 0:
                index += newline
                continue
            break
        candidate = rest[:end + 1]
        match = MARKER.fullmatch(candidate)
        if match and match[1] in allowed:
            output.append(candidate)
        index += end + 1
    return "".join(output)


class CitationStream:
    def __init__(self, evidence):
        self.evidence = evidence
        self.raw = ""
        self.sent = 0

    def feed(self, text):
        self.raw += text
        visible = clean(self.raw, self.evidence)
        delta = visible[self.sent:]
        self.sent = len(visible)
        return delta


def finish(answer, evidence):
    answer = clean(answer, evidence)
    used = set(MARKER.findall(answer))
    sources = [source for source in evidence.sources()
               if source["kind"] == "web" or source["marker"] in used]
    return answer, sources


def source_text(session, source_id):
    from app.services import guest
    from app.services.conversations import ensure_active

    with session.lock:
        ensure_active(session)
        if session.conversation_id is None:
            raise ServiceError(404, "Source no longer available")
        messages = (guest.messages(session) if session.guest else
                    repository.messages(session.user_id, conversation_id=session.conversation_id))
        source = next((source for message in messages if message["role"] == "assistant"
                       for source in message.get("sources", [])
                       if source.get("kind") == "document" and source.get("id") == source_id), None)
        if source is None:
            raise ServiceError(404, "Source no longer available")
        files = (session.uploads.values() if session.guest else
                 repository.conversation_files(session.user_id, session.conversation_id))
        exists = (any(item.id == source["file_id"] for item in files) if session.guest else
                  any(item["file_id"] == source["file_id"] and item["kind"] == "upload" for item in files))
        if not exists:
            raise ServiceError(404, "Source no longer available")
        return source
