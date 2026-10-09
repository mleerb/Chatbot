import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.agent import answer_question, make_agent
from app.context import MAX_HISTORY_MESSAGES
from app.dependencies import session_for

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


@router.get("/state")
def state(request: Request, response: Response):
    _, session = session_for(request, response)
    with session.lock:
        return {"messages": list(session.history), "filename": session.filename,
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
            sources = []
            try:
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
