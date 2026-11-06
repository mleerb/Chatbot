import logging
import os
from contextlib import contextmanager
from fnmatch import fnmatchcase
from typing import Iterator

from langfuse import Langfuse, propagate_attributes
from langfuse.langchain import CallbackHandler
from langfuse.types import MaskOtelSpansParams, MaskOtelSpansResult, OtelSpanPatch
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import StatusCode

from app.core.limits import positive

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


INTERNAL_STEPS = frozenset({
    "PatchToolCallsMiddleware.before_agent",
    "_ParentNotifierMiddleware.after_agent",
})


def excluded_route(scope: dict) -> bool:
    patterns = os.getenv("LANGFUSE_EXCLUDED_ROUTES", "/*").split(",")
    return any(fnmatchcase(scope.get("path", ""), pattern.strip())
               for pattern in patterns if pattern.strip())


def export_chat_span(span: ReadableSpan) -> bool:
    if span.instrumentation_scope is None or span.instrumentation_scope.name != "langfuse-sdk":
        return False
    if not span.attributes or not span.attributes.get("langfuse.observation.type"):
        return False
    return span.name not in INTERNAL_STEPS or (
        span.status.status_code == StatusCode.ERROR
        or span.attributes.get("langfuse.observation.level") == "ERROR"
    )


class ChatTraceHandler(CallbackHandler):
    def on_chat_model_start(self, serialized, messages, **kwargs):
        return super().on_chat_model_start(serialized, messages, **{
            **kwargs, "name": "generate-response",
        })

    def on_llm_start(self, serialized, prompts, **kwargs):
        return super().on_llm_start(serialized, prompts, **{
            **kwargs, "name": "generate-response",
        })


_client: Langfuse | None = None


def get_tracing_client() -> Langfuse:
    global _client
    if _client is None:
        _client = Langfuse(mask_otel_spans=mask_otel_spans, should_export_span=export_chat_span,
                           timeout=positive("LANGFUSE_TIMEOUT_SECONDS", 60, True))
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
                yield ChatTraceHandler(public_key=os.environ["LANGFUSE_PUBLIC_KEY"]), span
            except Exception:
                span.update(level="ERROR", status_message="Chat turn failed")
                raise
