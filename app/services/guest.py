import secrets

from app.core.errors import ServiceError
from app.services.context import MAX_HISTORY_MESSAGES
from app.services.sessions import GuestChat


def active(session):
    return session.guest_chats.get(session.conversation_id)


def conversation(session):
    chat = active(session)
    return dict(chat.conversation) if chat else None


def conversations(session):
    return [dict(chat.conversation) for chat in reversed(session.guest_chats.values())]


def messages(session):
    chat = active(session)
    return list(chat.messages) if chat else []


def activate(session, chat):
    session.conversation_id = chat.conversation["id"]
    session.uploads = chat.uploads
    session.generated = chat.generated
    session.history = chat.messages[-MAX_HISTORY_MESSAGES:]
    return dict(chat.conversation)


def create(session):
    identifier = -secrets.randbits(48) - 1
    number = len(session.guest_chats) + 1
    chat = GuestChat({
        "id": identifier, "user_id": 0, "title": "Temporary chat" if number == 1 else f"Temporary chat {number}",
        "pinned": False,
    })
    session.guest_chats[identifier] = chat
    return activate(session, chat)


def require(session, identifier):
    chat = session.guest_chats.get(identifier)
    if chat is None:
        raise ServiceError(404, "Conversation not found")
    return chat


def select(session, identifier):
    return activate(session, require(session, identifier))


def rename(session, identifier, title):
    chat = require(session, identifier)
    chat.conversation["title"] = title
    chat.named = True
    return dict(chat.conversation)



def remove(session, identifier):
    chat = session.guest_chats.pop(identifier, None)
    if chat is None:
        raise ServiceError(404, "Conversation not found")
    chat.uploads.clear()
    chat.generated.clear()
    if session.conversation_id != identifier:
        return
    remaining = next(reversed(session.guest_chats.values()), None)
    if remaining is not None:
        activate(session, remaining)
        return
    session.conversation_id = None
    session.uploads = {}
    session.generated = {}
    session.history = []
