from app.core.errors import ServiceError
from app.db import repository
from app.services.context import MAX_HISTORY_MESSAGES
from app.services.sessions import ChatSession


def require_user(session: ChatSession):
    if session.user_id is None:
        raise ServiceError(400, "Select a user first")
    return session.user_id


def activate(session: ChatSession, conversation):
    if session.conversation_id != conversation["id"]:
        session.clear_upload()
        session.generated.clear()
    session.conversation_id = conversation["id"]
    session.history = repository.messages(session.user_id, MAX_HISTORY_MESSAGES, session.conversation_id)
    return conversation


def list_conversations(session: ChatSession):
    with session.lock:
        return repository.conversations(require_user(session))


def create(session: ChatSession):
    with session.lock:
        return activate(session, repository.create_conversation(require_user(session)))


def select(session: ChatSession, conversation_id: int):
    with session.lock:
        conversation = repository.get_conversation(require_user(session), conversation_id)
        if conversation is None:
            raise ServiceError(404, "Conversation not found")
        return activate(session, conversation)


def update(session: ChatSession, conversation_id: int, title: str | None, pinned: bool | None):
    if title is not None:
        title = title.strip()
        if not title:
            raise ServiceError(422, "Title cannot be blank")
    with session.lock:
        conversation = repository.update_conversation(require_user(session), conversation_id, title, pinned)
        if conversation is None:
            raise ServiceError(404, "Conversation not found")
        return conversation


def remove(session: ChatSession, conversation_id: int):
    with session.lock:
        if repository.delete_conversation(require_user(session), conversation_id) is None:
            raise ServiceError(404, "Conversation not found")
        if session.conversation_id == conversation_id:
            session.conversation_id = None
            session.history.clear()
            session.clear_upload()
            session.generated.clear()
            remaining = repository.conversations(session.user_id)
            if remaining:
                activate(session, remaining[0])
        return {"ok": True}


def ensure_active(session: ChatSession):
    if session.conversation_id is not None and repository.get_conversation(
        session.user_id, session.conversation_id
    ) is None:
        session.conversation_id = None
        session.history.clear()
        session.clear_upload()
        session.generated.clear()
