import os
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch

from deepagents import create_deep_agent
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app import trace


class FakeToolsChatModel(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class TracingTests(unittest.TestCase):
    def test_disabled_without_credentials(self):
        with patch.dict(os.environ, {}, clear=True):
            with trace.trace_chat_turn(
                session_id="test-session", question="Hi", model="fake", has_document=False
            ) as (handler, span):
                self.assertIsNone(handler)
                self.assertIsNone(span)

    def test_failed_turn_marks_root_error_without_leaking_exception(self):
        span = Mock()
        client = Mock()

        @contextmanager
        def observation(**kwargs):
            yield span

        client.start_as_current_observation.side_effect = observation
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
            "LANGFUSE_BASE_URL": "http://localhost:9999",
        }), patch('app.trace.get_tracing_client', return_value=client):
            with self.assertRaisesRegex(ValueError, "Private failure detail"):
                with trace.trace_chat_turn(
                    session_id="test-session", question="Private question",
                    model="fake", has_document=False,
                ):
                    raise ValueError("Private failure detail")
        span.update.assert_called_once_with(level="ERROR", status_message="Chat turn failed")

    def test_agent_trace_is_nested_and_content_redacted(self):
        exporter = InMemorySpanExporter()
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
            "LANGFUSE_BASE_URL": "http://localhost:9999",
            "LANGFUSE_TRACE_CONTENT": "false",
        }), patch.object(trace, "_client", Langfuse(
            public_key="pk-lf-test", secret_key="sk-lf-test",
            base_url="http://localhost:9999", span_exporter=exporter,
            mask_otel_spans=trace.mask_otel_spans,
        )):
            agent = create_deep_agent(
                model=FakeToolsChatModel(responses=["The answer is 42."]),
                system_prompt="A test",
            )
            with trace.trace_chat_turn(
                session_id="test-session", question="Top secret question",
                model="fake", has_document=True,
            ) as (handler, span):
                result = agent.invoke({"messages": [{
                    "role": "user", "content": "Top secret document\nTop secret question"
                }]}, config={"callbacks": [handler]})
                span.update(output=result["messages"][-1].content)
            trace._client.flush()

        spans = exporter.get_finished_spans()
        root = next(s for s in spans if s.name == "chat-response")
        self.assertIsNone(root.parent)
        self.assertEqual(root.attributes["session.id"], "test-session")
        self.assertEqual(root.attributes["langfuse.observation.metadata.model"], "fake")
        self.assertTrue(any(
            s.attributes.get("langfuse.observation.type") == "generation" for s in spans
        ))
        self.assertTrue(all(
            "Top secret" not in str(s.attributes)
            and "The answer is 42" not in str(s.attributes) for s in spans
        ))


if __name__ == "__main__":
    unittest.main()
