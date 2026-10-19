from fastapi import APIRouter

from app.dependencies import Session
from app.schemas.chat import Message
from app.schemas.users import UserRequest, UserResponse
from app.services import users as service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def list_users():
    return service.list_users()


@router.post("", response_model=UserResponse, status_code=201)
def add_user(payload: UserRequest):
    return service.create_user(payload.name)


@router.post("/{user_id}/select", response_model=UserResponse)
def select_user(user_id: int, current: Session):
    return service.select_user(current[1], user_id)


@router.get("/{user_id}/messages", response_model=list[Message])
def user_messages(user_id: int, current: Session):
    return service.messages(current[1], user_id)
