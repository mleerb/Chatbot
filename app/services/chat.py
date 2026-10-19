import logging

from app.core.errors import ServiceError
from app.db import repository
from app.services.agent import answer_question, make_agent
from app.services.context import MAX_HISTORY_MESSAGES
from app.services.sessions import ChatSession

logger = logging.getLogger(__name__)


def state(session: ChatSession):
    with session.lock:
        return {
            "user_id": session.user_id,
            "messages": repository.messages(session.user_id) if session.user_id else [],
            **session.file_state(),
        }


def reply(token: str, session: ChatSession, message: str):
    question = message.strip()
    if not question:
        raise ServiceError(422, "Message cannot be blank")
    with session.lock:
        if session.user_id is None:
            raise ServiceError(400, "Select a user before chatting")
        sources = []
        try:
            session.history = repository.messages(session.user_id, MAX_HISTORY_MESSAGES)
            answer = answer_question(
                make_agent(token, question, sources), question, session.history, token,
                uploads=list(session.uploads.values()),
            )
        except Exception as exc:
            logger.exception("Chat request failed")
            raise ServiceError(502, "Could not get an answer. Check the server log and model settings.") from exc
        links = list(dict.fromkeys((item["title"], item["url"]) for item in sources))
        citations = [{"title": title, "url": url} for title, url in links]
        linked_answer = answer
        if links:
            linked_answer += "\n\nWeb sources:\n" + "\n".join(
                f"{title}: {url}" for title, url in links
            )
        try:
            repository.save_turn(session.user_id, question, answer, citations)
        except Exception as exc:
            logger.exception("Could not save chat turn")
            raise ServiceError(503, "Could not save conversation") from exc
        session.history.extend([
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer, "sources": citations},
        ])
        session.history = session.history[-MAX_HISTORY_MESSAGES:]
        return {
            "answer": linked_answer,
            "display_answer": answer,
            **session.file_state(),
            "sources": citations,
        }
