from fastapi import APIRouter, HTTPException

from app.dependencies import AccountSession as Session
from app.schemas.chat import Message
from app.schemas.users import UserRequest, UserResponse
from app.services import users as service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def list_users(current: Session):
    return [current[1].account]


@router.post("", response_model=UserResponse, status_code=201)
def add_user(payload: UserRequest, current: Session):
    raise HTTPException(status_code=403, detail="Use account registration instead")


@router.post("/{user_id}/select", response_model=UserResponse)
def select_user(user_id: int, current: Session):
    if current[1].user_id != user_id:
        raise HTTPException(status_code=403, detail="You cannot access another account")
    service.select_user(current[1], user_id)
    return current[1].account


@router.get("/{user_id}/messages", response_model=list[Message])
def user_messages(user_id: int, current: Session):
    return service.messages(current[1], user_id)
