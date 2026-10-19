import psycopg

from app.core.errors import ServiceError
from app.db import repository
from app.services.context import MAX_HISTORY_MESSAGES
from app.services.sessions import ChatSession


def list_users():
    return repository.users()


def create_user(name: str):
    name = name.strip()
    if not name:
        raise ServiceError(422, "Name cannot be blank")
    try:
        return repository.create_user(name)
    except psycopg.errors.UniqueViolation as exc:
        raise ServiceError(409, "User name already exists") from exc


def select_user(session: ChatSession, user_id: int):
    with session.lock:
        user = repository.get_user(user_id)
        if user is None:
            raise ServiceError(404, "User not found")
        if session.user_id != user_id:
            session.clear_upload()
            session.generated.clear()
        session.user_id = user_id
        session.history = repository.messages(user_id, MAX_HISTORY_MESSAGES)
        return user


def messages(session: ChatSession, user_id: int):
    with session.lock:
        if session.user_id != user_id:
            raise ServiceError(403, "Select this user first")
        return repository.messages(user_id)
