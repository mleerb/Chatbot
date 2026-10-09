import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from deepagents import create_deep_agent

from app.context import conversation_messages, response_text
from app.model import chat_model
from app.prompts import render_prompt
from app.tools import tools_for_turn
from app.trace import trace_chat_turn


def make_agent(session_id: str | None = None, question: str = "", sources: list[dict] | None = None):
    return create_deep_agent(
        model=chat_model(),
        tools=tools_for_turn(session_id, question, sources),
        system_prompt=render_prompt("system.j2"),
    )


def answer_question(agent, question: str, history: list[dict], session_id: str,
                    document_text: str = "", image_url: str = "", filename: str = "") -> str:
    messages = conversation_messages(question, history, document_text, image_url, filename)
    with trace_chat_turn(
        session_id=session_id,
        question=question,
        model=os.getenv("CHAT_MODEL", "openai:gpt-4o-mini").strip(),
        has_document=bool(filename),
    ) as (handler, span):
        config = {"callbacks": [handler]} if handler else None
        result = agent.invoke({"messages": messages}, config=config)
        answer = response_text(result["messages"][-1].content)
        if not answer:
            raise ValueError("Model returned an empty response")
        if span is not None:
            span.update(output=answer)
    return answer
