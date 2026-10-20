from fastapi import APIRouter

from app.dependencies import Session
from app.schemas.conversations import ConversationResponse, ConversationUpdate, DeleteResponse
from app.services import conversations as service

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationResponse])
def list_conversations(current: Session):
    return service.list_conversations(current[1])


@router.post("", response_model=ConversationResponse, status_code=201)
def create_conversation(current: Session):
    return service.create(current[1])


@router.post("/{conversation_id}/select", response_model=ConversationResponse)
def select_conversation(conversation_id: int, current: Session):
    return service.select(current[1], conversation_id)


@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(conversation_id: int, payload: ConversationUpdate, current: Session):
    return service.update(current[1], conversation_id, payload.title, payload.pinned)


@router.delete("/{conversation_id}", response_model=DeleteResponse)
def delete_conversation(conversation_id: int, current: Session):
    return service.remove(current[1], conversation_id)
