import logging
import os
from contextlib import contextmanager
from typing import Iterator

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler
from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult, OtelSpanPatch

logger = logging.getLogger(__name__)

REDACTED = "[REDACTED: set LANGFUSE_TRACE_CONTENT=true to capture content]"
CONTENT_KEYS = (
    "input", "output", "prompt", "completion", "message", "content",
    "metadata", "argument", "result", "status_message", "exception",
)


def tracing_enabled() -> bool:
    return all(os.getenv(key) for key in (
        "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"
    ))


def mask_otel_spans(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult | None:
    if os.getenv("LANGFUSE_TRACE_CONTENT", "false").lower() == "true":
        return None
    patches = {}
    for identifier, span in params.spans.items():
        replacements = {
            key: REDACTED
            for key in span.attributes
            if any(part in key.lower() for part in CONTENT_KEYS)
            and key not in (
                "langfuse.observation.metadata.model",
                "langfuse.observation.metadata.has_document",
            )
            and not key.startswith(("gen_ai.usage.", "langfuse.observation.model"))
        }
        if replacements:
            patches[identifier] = OtelSpanPatch(set_attributes=replacements)
    return MaskOtelSpansResult(span_patches=patches) if patches else None


_client: Langfuse | None = None


def get_tracing_client() -> Langfuse:
    global _client
    if _client is None:
        _client = Langfuse(mask_otel_spans=mask_otel_spans)
    return _client


def score_answer(trace_id: str, rating: str | None) -> None:
    if not tracing_enabled():
        return
    try:
        get_tracing_client().create_score(
            name="user-feedback", value={"up": 1, "down": -1}.get(rating, 0), data_type="NUMERIC",
            trace_id=trace_id, score_id=f"{trace_id}-feedback",
        )
    except Exception:
        logger.exception("Could not send answer feedback to Langfuse")


def flush_traces() -> None:
    if _client is not None:
        _client.flush()


@contextmanager
def trace_chat_turn(*, session_id: str, question: str, model: str,
                    has_document: bool) -> Iterator[tuple[CallbackHandler | None, object | None]]:
    if not tracing_enabled():
        yield None, None
        return

    client = get_tracing_client()
    with client.start_as_current_observation(
        as_type="span", name="chat-response", input=question,
        metadata={"model": model, "has_document": has_document},
    ) as span:
        with propagate_attributes(session_id=session_id, tags=["document-chat"]):
            try:
                yield CallbackHandler(), span
            except Exception:
                span.update(level="ERROR", status_message="Chat turn failed")
                raise
