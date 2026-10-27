import os
import re
import secrets
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import date

from app.core.errors import ServiceError
from app.services import quota
from app.services.context import MAX_HISTORY_MESSAGES
from app.services.sessions import GuestChat

GUEST_TOKEN_LIMIT = int(os.getenv("GUEST_TOKEN_LIMIT", "50000"))
GUEST_IMAGE_LIMIT = int(os.getenv("GUEST_IMAGE_LIMIT", "2"))
METER_COOKIE_AGE = 30 * 24 * 60 * 60
MAX_METERS = 10_000
LIMIT_MESSAGE = "Guest limit reached. Guest chat is available again after midnight; log in or sign up to keep chatting now."


@dataclass
class Meter:
    tokens: int = 0
    uploads: int = 0
    images: int = 0
    day: date | None = None


meters: OrderedDict[str, Meter] = OrderedDict()
meters_lock = threading.Lock()


def meter_id(value):
    return value if value and re.fullmatch(r"[A-Za-z0-9_-]{16,64}", value) else secrets.token_urlsafe(24)


def meter(session):
    key = session.guest_meter or ""
    today = quota.today()
    with meters_lock:
        item = meters.get(key)
        if item is None:
            item = meters[key] = Meter()
            while len(meters) > MAX_METERS:
                meters.popitem(last=False)
        if item.day != today:
            item.tokens, item.uploads, item.images, item.day = 0, 0, 0, today
        meters.move_to_end(key)
        return item


def limited(session):
    return meter(session).tokens >= GUEST_TOKEN_LIMIT


def resets_at(session):
    return quota.next_midnight() if limited(session) else None


def upload_resets_at(session):
    return quota.next_midnight() if meter(session).uploads >= quota.UPLOAD_LIMIT else None


def check_limit(session):
    if limited(session):
        raise ServiceError(403, LIMIT_MESSAGE)


def check_upload(session):
    check_limit(session)
    if upload_resets_at(session) is not None:
        raise ServiceError(403, quota.UPLOAD_LIMIT_MESSAGE)


def take_upload(session):
    item = meter(session)
    with meters_lock:
        if item.uploads >= quota.UPLOAD_LIMIT:
            raise ServiceError(403, quota.UPLOAD_LIMIT_MESSAGE)
        item.uploads += 1


def take_image(session):
    item = meter(session)
    with meters_lock:
        if item.images >= GUEST_IMAGE_LIMIT:
            return False
        item.images += 1
        return True


def release_image(session):
    item = meter(session)
    with meters_lock:
        item.images = max(item.images - 1, 0)


def add_usage(session, tokens):
    item = meter(session)
    with meters_lock:
        item.tokens += tokens


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
    for chat in session.guest_chats.values():
        chat.uploads.clear()
        chat.generated.clear()
    session.guest_chats.clear()
    identifier = -secrets.randbits(48) - 1
    chat = GuestChat({"id": identifier, "user_id": 0, "title": "Temporary chat", "pinned": False})
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
