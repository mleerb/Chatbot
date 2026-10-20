from pathlib import Path

from app.core.errors import ServiceError
from app.db import repository
from app.services import guest
from app.services.conversations import activate, ensure_active
from app.services.extract import file_context
from app.services.sessions import ChatSession, Upload


def upload(session: ChatSession, filename: str, data: bytes):
    filename = Path(filename.replace("\\", "/")).name
    if not filename:
        raise ServiceError(400, "Choose a file")
    text, image_url, status = file_context(filename, data)
    item = Upload(filename, data, text, image_url, status)
    with session.lock:
        if session.user_id is None and not session.guest:
            raise ServiceError(400, "Log in or continue as guest")
        ensure_active(session)
        if session.conversation_id is None:
            if session.guest:
                guest.create(session)
            else:
                activate(session, repository.create_conversation(session.user_id))
        session.uploads[item.id] = item
    return item.summary()


def find_upload(session: ChatSession, file_id: str | None) -> Upload:
    item = session.uploads.get(file_id) if file_id is not None else session.latest_upload
    if item is None:
        raise ServiceError(404, "Uploaded file not found")
    return item


def original(session: ChatSession, file_id: str | None = None) -> tuple[str, bytes]:
    with session.lock:
        item = find_upload(session, file_id)
        return item.filename, item.data


def edited(session: ChatSession, file_id: str | None = None,
           revision_id: str | None = None) -> tuple[str, bytes]:
    with session.lock:
        item = find_upload(session, file_id)
        revision = next((edit for edit in item.edits if edit.id == revision_id), None) if revision_id else (
            item.edits[-1] if item.edits else None
        )
        if revision is None:
            raise ServiceError(404, "Edited file not found")
        return revision.filename, revision.data


def generated(session: ChatSession, file_id: str | None = None) -> tuple[str, bytes]:
    with session.lock:
        item = session.generated.get(file_id) if file_id is not None else session.latest_generated
        if item is None:
            raise ServiceError(404, "Generated file not found")
        return item.filename, item.data


def remove(session: ChatSession, file_id: str | None = None):
    with session.lock:
        if file_id is None:
            session.clear_upload()
        else:
            item = find_upload(session, file_id)
            del session.uploads[item.id]
    return {"ok": True}
