import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.dependencies import Session
from app.schemas.chat import ChatRequest, ChatResponse, RatingRequest, RatingResponse, StateResponse, StopResponse
from app.services import chat as service

router = APIRouter(tags=["chat"])


@router.get("/state", response_model=StateResponse)
def state(current: Session):
    return service.state(current[1])


@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, current: Session):
    return service.reply(*current, payload.message, payload.replace_from)


def server_events(events):
    for event in events:
        if event["type"] == "done":
            event = {"type": "done", **ChatResponse.model_validate(event).model_dump(mode="json")}
        yield f"data: {json.dumps(event)}\n\n"


@router.post("/chat/stream", response_class=StreamingResponse)
def stream(payload: ChatRequest, current: Session):
    service.check(current[1], payload.message)
    return StreamingResponse(
        server_events(service.stream_reply(*current, payload.message, payload.replace_from)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/stop", response_model=StopResponse)
def stop(current: Session):
    return service.stop(current[1])


@router.post("/chat/rating", response_model=RatingResponse)
def rating(payload: RatingRequest, current: Session):
    return service.rate(current[1], payload.index, payload.rating)
