import logging
import re

from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage

from app.db.repository import DEFAULT_TITLE
from app.prompts import render_prompt
from app.services.context import response_text
from app.services.model import chat_model

logger = logging.getLogger(__name__)

MAX_TITLE = 60
MAX_FALLBACK = 50
MAX_EXCERPT = 1000


def shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0] or text[:limit]
    return cut.rstrip(" ,;:-") + "…"


def clean(text: str) -> str:
    line = next((part for part in text.splitlines() if part.strip()), "")
    line = re.sub(r"^(title\s*:\s*)", "", line.strip(), flags=re.IGNORECASE)
    line = line.strip(" \t#*_`\"'“”‘’").rstrip(".:;,")
    return shorten(line, MAX_TITLE)


def fallback(question: str) -> str:
    return shorten(question, MAX_FALLBACK) or DEFAULT_TITLE


def generate(question: str, answer: str) -> str:
    model = chat_model()
    if isinstance(model, str):
        model = init_chat_model(model)
    prompt = render_prompt("title.j2", question=question[:MAX_EXCERPT], answer=answer[:MAX_EXCERPT])
    return clean(response_text(model.invoke([HumanMessage(content=prompt)]).content))


def suggest(question: str, answer: str) -> str:
    try:
        title = generate(question, answer)
    except Exception:
        logger.warning("Could not generate a conversation title", exc_info=True)
        title = ""
    return title or fallback(question)
