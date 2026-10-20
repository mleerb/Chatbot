from app.core.errors import ServiceError
from app.db import repository
from app.services.conversations import activate
from app.services.sessions import ChatSession


def select_user(session: ChatSession, user_id: int):
    with session.lock:
        user = repository.get_user(user_id)
        if user is None:
            raise ServiceError(404, "User not found")
        changed = session.user_id != user_id
        if changed:
            session.clear_upload()
            session.generated.clear()
        session.user_id = user_id
        conversations = repository.conversations(user_id)
        current = next((item for item in conversations if item["id"] == session.conversation_id), None)
        if changed or current is None:
            current = conversations[0] if conversations else repository.create_conversation(user_id)
        activate(session, current)
        return user


def messages(session: ChatSession, user_id: int):
    with session.lock:
        if session.user_id != user_id:
            raise ServiceError(403, "Select this user first")
        return repository.messages(user_id)
