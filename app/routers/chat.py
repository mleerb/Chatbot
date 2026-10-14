import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.agent import answer_question, make_agent
from app.context import MAX_HISTORY_MESSAGES
from app.sessions import session_for
from app import database

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


@router.get("/state")
def state(request: Request, response: Response):
    _, session = session_for(request, response)
    with session.lock:
        return {"user_id": session.user_id, "messages": database.messages(session.user_id) if session.user_id else [],
                "filename": session.filename,
                "status": session.file_status, "generated_filename": session.generated_filename,
                "edited_filename": session.filename if session.edited_bytes is not None else ""}


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request, response: Response):
    token, session = session_for(request, response)
    question = payload.message.strip()
    if not question:
        raise HTTPException(status_code=422, detail="Message cannot be blank")

    def reply():
        with session.lock:
            if session.user_id is None:
                raise HTTPException(status_code=400, detail="Select a user before chatting")
            sources = []
            try:
                session.history = database.messages(session.user_id, MAX_HISTORY_MESSAGES)
                answer = answer_question(make_agent(token, question, sources), question, session.history, token,
                                         session.document, session.image_url, session.filename)
            except Exception as exc:
                logger.exception("Chat request failed")
                raise HTTPException(status_code=502, detail="Could not get an answer. Check the server log and model settings.") from exc
            links = list(dict.fromkeys((item["title"], item["url"]) for item in sources))
            citations = [{"title": title, "url": url} for title, url in links]
            linked_answer = answer
            if links:
                linked_answer += "\n\nWeb sources:\n" + "\n".join(
                    f"{title}: {url}" for title, url in links
                )
            try:
                database.save_turn(session.user_id, question, answer, citations)
            except Exception as exc:
                logger.exception("Could not save chat turn")
                raise HTTPException(status_code=503, detail="Could not save conversation") from exc
            session.history.extend([
                {"role": "user", "content": question},
                {"role": "assistant", "content": answer, "sources": citations},
            ])
            session.history = session.history[-MAX_HISTORY_MESSAGES:]
            return {"answer": linked_answer, "display_answer": answer,
                    "generated_filename": session.generated_filename,
                    "edited_filename": session.filename if session.edited_bytes is not None else "",
                    "sources": citations}

    return await run_in_threadpool(reply)
