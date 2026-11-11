import os
import threading
from collections.abc import Iterator
from contextlib import nullcontext

from deepagents import create_deep_agent
from langchain_core.messages import AIMessage, AIMessageChunk

from app.core.trace import trace_chat_turn
from app.prompts import render_prompt
from app.services.citations import current
from app.services.context import conversation_messages, response_text
from app.services.model import chat_model
from app.services.sessions import Upload
from app.services.steps import step_label
from app.tools import tools_for_turn


def make_agent(session_id: str | None = None, question: str = "", sources: list[dict] | None = None):
    return create_deep_agent(
        model=chat_model(),
        tools=tools_for_turn(session_id, question, sources),
        system_prompt=render_prompt("system.j2"),
    )


def used_tokens(messages) -> int:
    total = 0
    for message in messages:
        metadata = getattr(message, "usage_metadata", None)
        if isinstance(metadata, dict):
            total += metadata.get("total_tokens", 0)
    return total


def chunk_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(block.get("text", "") for block in content
                       if isinstance(block, dict) and block.get("type") == "text")
    return ""


def observe(trace_session: str | None, question: str, uploads: list[Upload] | None, trace: bool, guest: bool):
    if not trace:
        return nullcontext((None, None))
    return trace_chat_turn(
        session_id=trace_session,
        question=question,
        model=os.getenv("CHAT_MODEL", "openai:gpt-4o-mini").strip(),
        has_document=bool(uploads),
        guest=guest,
    )


def answer_question(agent, question: str, history: list[dict], session_id: str,
                    uploads: list[Upload] | None = None, trace: bool = True,
                    usage: list[int] | None = None, traces: list[str] | None = None,
                    trace_session: str | None = None, guest: bool = False) -> str:
    messages = conversation_messages(question, history, uploads, evidence=current(session_id))
    with observe(trace_session, question, uploads, trace, guest) as (handler, span):
        config = {"callbacks": [handler]} if handler else None
        result = agent.invoke({"messages": messages}, config=config)
        answer = response_text(result["messages"][-1].content)
        if not answer:
            raise ValueError("Model returned an empty response")
        if usage is not None:
            usage.append(used_tokens(result["messages"]))
        if span is not None:
            span.update(output=answer)
            if traces is not None:
                traces.append(span.trace_id)
    return answer


def stream_answer(agent, question: str, history: list[dict], session_id: str,
                  uploads: list[Upload] | None = None, trace: bool = True,
                  usage: list[int] | None = None, traces: list[str] | None = None,
                  stop: threading.Event | None = None, trace_session: str | None = None,
                  guest: bool = False) -> Iterator[dict]:
    messages = conversation_messages(question, history, uploads, evidence=current(session_id))
    filenames = {item.id: item.filename for item in uploads or []}
    with observe(trace_session, question, uploads, trace, guest) as (handler, span):
        config = {"callbacks": [handler]} if handler else None
        draft, answer, total, stopped = [], "", 0, False
        stream = agent.stream({"messages": messages}, config=config, stream_mode=["messages", "updates"])
        try:
            for mode, data in stream:
                if stop is not None and stop.is_set():
                    stopped = True
                    break
                if mode == "messages":
                    chunk, metadata = data
                    if isinstance(chunk, AIMessageChunk) and metadata.get("langgraph_node") == "model":
                        text = chunk_text(chunk.content)
                        if text:
                            draft.append(text)
                            yield {"type": "text", "text": text}
                    continue
                update = data.get("model") if isinstance(data, dict) else None
                for message in update.get("messages", []) if isinstance(update, dict) else []:
                    if not isinstance(message, AIMessage):
                        continue
                    total += used_tokens([message])
                    if message.tool_calls:
                        draft.clear()
                        for call in message.tool_calls:
                            yield {"type": "step", "label": step_label(call, filenames)}
                    else:
                        answer = response_text(message.content)
        finally:
            stream.close()
        if stopped:
            answer = "".join(draft).strip()
        elif not answer:
            raise ValueError("Model returned an empty response")
        if usage is not None:
            usage.append(total)
        if span is not None:
            span.update(output=answer)
            if traces is not None:
                traces.append(span.trace_id)
    yield {"type": "end", "answer": answer, "stopped": stopped}
