import logging

from app.core.errors import ServiceError
from app.db import repository
from app.services import guest
from app.services.agent import answer_question, make_agent
from app.services.context import MAX_HISTORY_MESSAGES
from app.services.conversations import activate, ensure_active
from app.services.sessions import ChatSession
from app.services.title import suggest as suggest_title

logger = logging.getLogger(__name__)


def state(session: ChatSession):
    with session.lock:
        ensure_active(session)
        if session.guest:
            return {"user_id": None, "conversation_id": session.conversation_id,
                    "conversations": guest.conversations(session), "messages": guest.messages(session),
                    **session.file_state()}
        return {
            "user_id": session.user_id,
            "conversation_id": session.conversation_id,
            "conversations": repository.conversations(session.user_id) if session.user_id else [],
            "messages": repository.messages(session.user_id, conversation_id=session.conversation_id)
            if session.conversation_id else [],
            **session.file_state(),
        }



def name_conversation(session: ChatSession, question: str, answer: str):
    try:
        conversation = repository.get_conversation(session.user_id, session.conversation_id)
        if conversation is not None and conversation["title"] == repository.DEFAULT_TITLE:
            repository.update_conversation(session.user_id, session.conversation_id, suggest_title(question, answer))
    except Exception:
        logger.exception("Could not name conversation")


def reply(token: str, session: ChatSession, message: str):
    question = message.strip()
    if not question:
        raise ServiceError(422, "Message cannot be blank")
    with session.lock:
        if session.user_id is None and not session.guest:
            raise ServiceError(400, "Log in or continue as guest")
        ensure_active(session)
        if session.conversation_id is None:
            if session.guest:
                guest.create(session)
            else:
                activate(session, repository.create_conversation(session.user_id))
        sources = []
        try:
            session.history = (guest.active(session).messages[-MAX_HISTORY_MESSAGES:] if session.guest else
                               repository.messages(session.user_id, MAX_HISTORY_MESSAGES, session.conversation_id))
            first_turn = not session.history
            answer = answer_question(
                make_agent(token, question, sources), question, session.history, token,
                uploads=list(session.uploads.values()), **({"trace": False} if session.guest else {}),
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
        unsent = [item for item in session.uploads.values() if not item.sent]
        attachments = [{"id": item.id, "filename": item.filename} for item in unsent]
        turn = [
            {"role": "user", "content": question, "attachments": attachments},
            {"role": "assistant", "content": answer, "sources": citations},
        ]
        if session.guest:
            chat = guest.active(session)
            chat.messages.extend(turn)
            if first_turn and not chat.named:
                guest.rename(session, session.conversation_id, suggest_title(question, answer))
        else:
            try:
                repository.save_turn(session.user_id, question, answer, citations, session.conversation_id, attachments)
            except Exception as exc:
                logger.exception("Could not save chat turn")
                raise ServiceError(503, "Could not save conversation") from exc
            if first_turn:
                name_conversation(session, question, answer)
        for item in unsent:
            item.sent = True
        session.history.extend(turn)
        session.history = session.history[-MAX_HISTORY_MESSAGES:]
        return {
            "answer": linked_answer,
            "display_answer": answer,
            **session.file_state(),
            "sources": citations,
        }
