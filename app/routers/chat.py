from fastapi import APIRouter

from app.dependencies import Session
from app.schemas.chat import ChatRequest, ChatResponse, StateResponse
from app.services import chat as service

router = APIRouter(tags=["chat"])


@router.get("/state", response_model=StateResponse)
def state(current: Session):
    return service.state(current[1])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current: Session):
    return service.reply(*current, payload.message)
