from app.db import repository
from app.services.sessions import ChatSession, Download, Page, Upload


def persistent(session: ChatSession) -> bool:
    return not session.guest and session.user_id is not None and session.conversation_id is not None


def page_rows(item: Upload) -> list[tuple[str, str]]:
    return [(page.label, page.text) for page in item.pages]


def load(session: ChatSession):
    session.uploads = {}
    session.generated = {}
    if not persistent(session):
        return
    sent = repository.attached_file_ids(session.user_id, session.conversation_id)
    for row in repository.conversation_files(session.user_id, session.conversation_id):
        if row["kind"] == "upload":
            session.uploads[row["file_id"]] = Upload(
                row["filename"], row["data"], row["document"], row["image_url"], row["status"], id=row["file_id"],
                pages=[Page(label, text) for label, text in row["pages"]], sent=row["file_id"] in sent,
            )
        elif row["kind"] == "generated":
            session.generated[row["file_id"]] = Download(row["filename"], row["data"], id=row["file_id"])
        elif (parent := session.uploads.get(row["parent_id"])) is not None:
            parent.edits.append(Download(row["filename"], row["data"], id=row["file_id"]))


def save_upload(session: ChatSession, item: Upload):
    if persistent(session):
        repository.save_file(session.user_id, session.conversation_id, "upload", item.id, item.filename, item.data,
                             item.document, item.image_url, item.status, page_rows(item))


def save_revision(session: ChatSession, item: Upload, revision: Download):
    if persistent(session):
        repository.save_file(session.user_id, session.conversation_id, "revision", revision.id, revision.filename,
                             revision.data, parent_id=item.id)
        repository.update_file_text(session.user_id, item.id, item.document, item.image_url, item.status,
                                    page_rows(item))


def save_generated(session: ChatSession, item: Download):
    if persistent(session):
        repository.save_file(session.user_id, session.conversation_id, "generated", item.id, item.filename, item.data)


def remove(session: ChatSession, file_id: str | None = None):
    if persistent(session):
        repository.delete_files(session.user_id, session.conversation_id, file_id)
