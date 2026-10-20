import secrets

from app.core.errors import ServiceError


def conversation(session):
    if session.guest_conversation is None:
        return None
    return dict(session.guest_conversation)


def create(session):
    session.guest_messages.clear()
    session.history.clear()
    session.uploads.clear()
    session.generated.clear()
    session.conversation_id = -secrets.randbits(48) - 1
    session.guest_conversation = {
        "id": session.conversation_id, "user_id": 0, "title": "Temporary chat", "pinned": False,
    }
    return conversation(session)


def require(session, identifier):
    if session.guest_conversation is None or session.conversation_id != identifier:
        raise ServiceError(404, "Conversation not found")
    return conversation(session)


def clear(session):
    session.guest_conversation = None
    session.conversation_id = None
    session.guest_messages.clear()
    session.history.clear()
    session.uploads.clear()
    session.generated.clear()
