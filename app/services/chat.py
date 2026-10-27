import logging
import queue
import threading

from app.core.errors import ServiceError
from app.core.trace import score_answer
from app.db import repository
from app.services import guest, images, quota
from app.services.agent import answer_question, make_agent, stream_answer
from app.services.context import MAX_HISTORY_MESSAGES
from app.services.pages import estimate_tokens
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
                    "guest_limited": guest.limited(session), "limit_resets_at": guest.resets_at(session),
                    "upload_resets_at": guest.upload_resets_at(session),
                    **session.file_state()}
        return {
            "user_id": session.user_id,
            "conversation_id": session.conversation_id,
            "conversations": repository.conversations(session.user_id) if session.user_id else [],
            "messages": repository.messages(session.user_id, conversation_id=session.conversation_id)
            if session.conversation_id else [],
            "limit_resets_at": quota.resets_at(session.user_id),
            "upload_resets_at": quota.upload_resets_at(session.user_id),
            **session.file_state(),
        }


def name_conversation(session: ChatSession, question: str, answer: str):
    try:
        conversation = repository.get_conversation(session.user_id, session.conversation_id)
        if conversation is not None and conversation["title"] == repository.DEFAULT_TITLE:
            repository.update_conversation(session.user_id, session.conversation_id, suggest_title(question, answer))
    except Exception:
        logger.exception("Could not name conversation")


def check(session: ChatSession, message: str):
    if not message.strip():
        raise ServiceError(422, "Message cannot be blank")
    if session.user_id is None and not session.guest:
        raise ServiceError(400, "Log in or continue as guest")
    if session.guest:
        guest.check_limit(session)
    else:
        quota.check_limit(session.user_id)


def earlier_messages(session: ChatSession, replace_from: int | None):
    if replace_from is None:
        return (guest.active(session).messages[-MAX_HISTORY_MESSAGES:] if session.guest else
                repository.messages(session.user_id, MAX_HISTORY_MESSAGES, session.conversation_id)), []
    every = (guest.messages(session) if session.guest else
             repository.messages(session.user_id, conversation_id=session.conversation_id))
    if not 0 <= replace_from < len(every) or every[replace_from]["role"] != "user":
        raise ServiceError(404, "Message not found")
    return every[:replace_from][-MAX_HISTORY_MESSAGES:], list(every[replace_from].get("attachments") or [])


def turn(token: str, session: ChatSession, message: str, replace_from: int | None, produce,
         stop: threading.Event | None = None):
    question = message.strip()
    with session.lock:
        check(session, question)
        ensure_active(session)
        if session.conversation_id is None:
            if replace_from is not None:
                raise ServiceError(404, "Message not found")
            if session.guest:
                guest.create(session)
            else:
                activate(session, repository.create_conversation(session.user_id))
        session.stopping = stop
        try:
            return finish_turn(token, session, question, replace_from, produce)
        finally:
            session.stopping = None


def finish_turn(token: str, session: ChatSession, question: str, replace_from: int | None, produce):
    sources = []
    usage = []
    traces = []
    existing = set(session.generated)
    try:
        session.history, kept = earlier_messages(session, replace_from)
        first_turn = not session.history
        answer, stopped = produce(
            make_agent(token, question, sources), question, session.history, token,
            uploads=list(session.uploads.values()), usage=usage, traces=traces,
            **({"trace": False} if session.guest else {}),
        )
    except ServiceError:
        raise
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
    kept_ids = {item.get("id") for item in kept}
    attachments = kept + [{"id": item.id, "filename": item.filename} for item in unsent if item.id not in kept_ids]
    created = [item.summary() for key, item in session.generated.items()
               if key not in existing and images.is_png(item.filename, item.data)]
    trace_id = traces[0] if traces else None
    turn_messages = [
        {"role": "user", "content": question, "attachments": attachments},
        {"role": "assistant", "content": answer, "sources": citations, "attachments": created,
         "stopped": stopped, "rating": None},
    ]
    tokens = sum(usage) or estimate_tokens(question + answer)
    if session.guest:
        guest.add_usage(session, tokens)
        chat = guest.active(session)
        if replace_from is None:
            chat.messages.extend(turn_messages)
        else:
            chat.messages[replace_from:] = turn_messages
        if first_turn and not chat.named:
            guest.rename(session, session.conversation_id, suggest_title(question, answer))
    else:
        try:
            repository.save_turn(session.user_id, question, answer, citations, session.conversation_id, attachments,
                                 created, stopped=stopped, trace_id=trace_id, replace_from=replace_from)
        except Exception as exc:
            logger.exception("Could not save chat turn")
            raise ServiceError(503, "Could not save conversation") from exc
        try:
            quota.record(session.user_id, tokens)
        except Exception:
            logger.exception("Could not record token usage")
        if first_turn:
            name_conversation(session, question, answer)
    for item in unsent:
        item.sent = True
    session.history = (session.history + turn_messages)[-MAX_HISTORY_MESSAGES:]
    return {
        "answer": linked_answer,
        "display_answer": answer,
        "stopped": stopped,
        **session.file_state(),
        "sources": citations,
        "attachments": created,
        "guest_limited": session.guest and guest.limited(session),
        "limit_resets_at": guest.resets_at(session) if session.guest else quota.resets_at(session.user_id),
    }


def reply(token: str, session: ChatSession, message: str, replace_from: int | None = None):
    def produce(agent, *args, **kwargs):
        return answer_question(agent, *args, **kwargs), False

    return turn(token, session, message, replace_from, produce)


def stream_reply(token: str, session: ChatSession, message: str, replace_from: int | None = None):
    events = queue.Queue()
    stop = threading.Event()

    def produce(agent, *args, **kwargs):
        result = {"answer": "", "stopped": False}
        for event in stream_answer(agent, *args, stop=stop, **kwargs):
            if event["type"] == "end":
                result = event
            else:
                events.put(event)
        return result["answer"], result["stopped"]

    def run():
        try:
            events.put({"type": "done", **turn(token, session, message, replace_from, produce, stop)})
        except ServiceError as exc:
            events.put({"type": "error", "status": exc.status_code, "detail": exc.detail})
        except Exception:
            logger.exception("Streaming chat failed")
            events.put({"type": "error", "status": 500, "detail": "Could not get an answer."})
        finally:
            events.put(None)

    threading.Thread(target=run, daemon=True).start()
    finished = False
    try:
        while (event := events.get()) is not None:
            yield event
        finished = True
    finally:
        if not finished:
            stop.set()


def stop(session: ChatSession):
    event = session.stopping
    if event is not None:
        event.set()
    return {"stopped": event is not None}


def rate(session: ChatSession, index: int, rating: str | None):
    with session.lock:
        ensure_active(session)
        if session.guest:
            chat = guest.active(session)
            items = chat.messages if chat else []
            if not 0 <= index < len(items) or items[index]["role"] != "assistant":
                raise ServiceError(404, "Message not found")
            items[index]["rating"] = rating
            return {"rating": rating}
        if session.user_id is None or session.conversation_id is None:
            raise ServiceError(404, "Message not found")
        rated = repository.rate_message(session.user_id, session.conversation_id, index, rating)
        if rated is None:
            raise ServiceError(404, "Message not found")
    if rated["trace_id"]:
        score_answer(rated["trace_id"], rating)
    return {"rating": rating}
