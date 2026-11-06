import logging
from pathlib import Path

from app.core import limits
from app.core.errors import ServiceError
from app.db import repository
from app.services import embed, guest, images, quota, storage, workspace
from app.services.conversations import activate, ensure_active
from app.services.extract import upload_context
from app.services.sessions import ChatSession, Upload

logger = logging.getLogger(__name__)


def check_capacity(session: ChatSession, size: int):
    limits.check_upload(size)
    if session.guest:
        limits.check_upload(size, len(session.uploads), sum(len(item.data) for item in session.uploads.values()))
    elif session.conversation_id is not None:
        repository.check_upload_capacity(session.user_id, session.conversation_id, size)


def upload(session: ChatSession, filename: str, data: bytes):
    filename = Path(filename.replace("\\", "/")).name
    if not filename:
        raise ServiceError(400, "Choose a file")
    with session.lock:
        ensure_active(session)
        check_capacity(session, len(data))
    if session.guest:
        guest.check_upload(session)
    else:
        quota.check_upload(session.user_id)
    inspection = {} if workspace.enabled(session) else None
    text, image_url, status, pages = upload_context(filename, data, session.parsed, **(
        {"inspection": inspection} if inspection is not None else {}
    ))
    item = Upload(filename, data, text, image_url, status, pages=pages)
    embed.prepare(item)
    from app.services.pages import is_large

    if is_large(item) and not item.embeddings:
        item.status += " Semantic search unavailable; keyword search will be used."
    with session.lock:
        if session.user_id is None and not session.guest:
            raise ServiceError(400, "Log in or continue as guest")
        ensure_active(session)
        check_capacity(session, len(data))
        if session.guest:
            guest.take_upload(session)
        else:
            quota.take_upload(session.user_id)
        if session.conversation_id is None:
            if session.guest:
                guest.create(session)
            else:
                activate(session, repository.create_conversation(session.user_id))
        try:
            storage.save_upload(session, item)
        except ServiceError:
            raise
        except Exception as exc:
            logger.exception("Could not save uploaded file")
            raise ServiceError(503, "Could not save the file") from exc
        session.uploads[item.id] = item
        if inspection is not None:
            workspace.export_upload(session, item, inspection)
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


def generated_image(session: ChatSession, file_id: str) -> tuple[str, bytes]:
    with session.lock:
        item = session.generated.get(file_id)
        if item is None or not images.is_png(item.filename, item.data):
            raise ServiceError(404, "Image not found")
        return item.filename, item.data


def remove(session: ChatSession, file_id: str | None = None):
    with session.lock:
        item = find_upload(session, file_id) if file_id is not None else None
        try:
            storage.remove(session, file_id)
        except Exception as exc:
            logger.exception("Could not remove stored file")
            raise ServiceError(503, "Could not remove the file") from exc
        if item is None:
            session.clear_upload()
        else:
            del session.uploads[item.id]
    return {"ok": True}
