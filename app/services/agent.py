import os
from deepagents import create_deep_agent

from app.services.context import conversation_messages, response_text
from app.services.model import chat_model
from app.prompts import render_prompt
from app.tools import tools_for_turn
from app.core.trace import trace_chat_turn
from app.services.sessions import Upload


def make_agent(session_id: str | None = None, question: str = "", sources: list[dict] | None = None):
    return create_deep_agent(
        model=chat_model(),
        tools=tools_for_turn(session_id, question, sources),
        system_prompt=render_prompt("system.j2"),
    )


def answer_question(agent, question: str, history: list[dict], session_id: str,
                    uploads: list[Upload] | None = None) -> str:
    messages = conversation_messages(question, history, uploads)
    with trace_chat_turn(
        session_id=session_id,
        question=question,
        model=os.getenv("CHAT_MODEL", "openai:gpt-4o-mini").strip(),
        has_document=bool(uploads),
    ) as (handler, span):
        config = {"callbacks": [handler]} if handler else None
        result = agent.invoke({"messages": messages}, config=config)
        answer = response_text(result["messages"][-1].content)
        if not answer:
            raise ValueError("Model returned an empty response")
        if span is not None:
            span.update(output=answer)
    return answer
