import psycopg
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.context import MAX_HISTORY_MESSAGES
from app.sessions import session_for
from app import database

router = APIRouter(prefix="/api/users", tags=["users"])


class UserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.get("")
def list_users():
    return database.users()


@router.post("", status_code=201)
def add_user(payload: UserRequest):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be blank")
    try:
        return database.create_user(name)
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="User name already exists") from exc


@router.post("/{user_id}/select")
def select_user(user_id: int, request: Request, response: Response):
    _, session = session_for(request, response)
    with session.lock:
        user = database.get_user(user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if session.user_id != user_id:
            session.clear_upload()
            session.generated_filename = ""
            session.generated_bytes = None
        session.user_id = user_id
        session.history = database.messages(user_id, MAX_HISTORY_MESSAGES)
        return user


@router.get("/{user_id}/messages")
def user_messages(user_id: int, request: Request, response: Response):
    _, session = session_for(request, response)
    with session.lock:
        if session.user_id != user_id:
            raise HTTPException(status_code=403, detail="Select this user first")
        return database.messages(user_id)
