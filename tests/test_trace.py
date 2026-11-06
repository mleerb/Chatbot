import json
import os
import unittest
from contextlib import contextmanager
from unittest.mock import Mock, patch
from uuid import uuid4

from deepagents import create_deep_agent
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel, FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from langfuse import Langfuse
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.trace import Status, StatusCode
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core import trace
from app.dependencies import session_for
from app.main import create_app
from app.services.sessions import ChatSession


class FakeToolsChatModel(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class FakeToolCallModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


class TracingTests(unittest.TestCase):
    @contextmanager
    def capture(self, content="false", raw_exporter=None):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        if raw_exporter is not None:
            provider.add_span_processor(SimpleSpanProcessor(raw_exporter))
        public_key = f"pk-lf-{uuid4()}"
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": public_key,
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
            "LANGFUSE_BASE_URL": "http://localhost:9999",
            "LANGFUSE_TRACE_CONTENT": content,
        }), patch("opentelemetry.trace.get_tracer_provider", return_value=provider):
            client = Langfuse(
                public_key=public_key, secret_key="sk-lf-test",
                base_url="http://localhost:9999", span_exporter=exporter,
                tracer_provider=provider,
                mask_otel_spans=trace.mask_otel_spans,
                should_export_span=trace.export_chat_span,
            )
            with patch.object(trace, "_client", client):
                try:
                    yield exporter
                finally:
                    client.flush()
                    client.shutdown()

    def assert_nested(self, spans):
        ids = {span.context.span_id for span in spans}
        roots = [span for span in spans if span.parent is None]
        self.assertEqual([span.name for span in roots], ["chat-response"])
        for span in spans:
            if span.parent is not None:
                self.assertIn(span.parent.span_id, ids)

    def test_internal_steps_are_filtered_but_errors_and_real_agents_are_kept(self):
        for name in trace.INTERNAL_STEPS:
            span = Mock(attributes={"langfuse.observation.type": "agent"}, status=Status(StatusCode.UNSET))
            span.instrumentation_scope.name = "langfuse-sdk"
            span.name = name
            self.assertFalse(trace.export_chat_span(span))
            span.status = Status(StatusCode.ERROR)
            self.assertTrue(trace.export_chat_span(span))
            span.status = Status(StatusCode.UNSET)
            span.attributes = {"langfuse.observation.type": "agent", "langfuse.observation.level": "ERROR"}
            self.assertTrue(trace.export_chat_span(span))
        for name in ["LangGraph", "model", "research-agent", "search_documents"]:
            span = Mock(attributes={"langfuse.observation.type": "span"}, status=Status(StatusCode.UNSET))
            span.instrumentation_scope.name = "langfuse-sdk"
            span.name = name
            self.assertTrue(trace.export_chat_span(span))

    def test_route_exclusions_default_to_all_automatic_request_telemetry(self):
        with patch.dict(os.environ, {}, clear=True):
            for path in ["/health", "/api/state", "/api/chat", "/api/chat/stream", "/api/auth/me", "/static/a.js"]:
                self.assertTrue(trace.excluded_route({"path": path}))
        with patch.dict(os.environ, {"LANGFUSE_EXCLUDED_ROUTES": " /health, /api/state, /static/* "}):
            for path in ["/health", "/api/state", "/static/a.js"]:
                self.assertTrue(trace.excluded_route({"path": path}))
            self.assertFalse(trace.excluded_route({"path": "/api/chat"}))
            self.assertFalse(trace.excluded_route({"path": "/health-other"}))
        with patch.dict(os.environ, {"LANGFUSE_EXCLUDED_ROUTES": ""}):
            self.assertFalse(trace.excluded_route({"path": "/health"}))

    def test_export_rejects_fastapi_http_and_other_infrastructure(self):
        with self.capture() as exporter:
            from opentelemetry import trace as otel_trace
            for scope, name in [("fastapi", "GET /health"), ("fastapi", "fastapi.dependencies"),
                                ("fastapi", "fastapi.endpoint"), ("fastapi", "fastapi.serialization"),
                                ("fastapi", "POST /api/chat"), ("httpx", "GET"), ("sqlalchemy", "SELECT")]:
                with otel_trace.get_tracer(scope).start_as_current_span(name) as span:
                    span.set_attribute("langfuse.observation.type", "span")
            trace.flush_traces()
            self.assertEqual(exporter.get_finished_spans(), ())

    def test_health_and_polling_produce_no_spans_but_chat_produces_one_trace(self):
        raw = InMemorySpanExporter()
        with self.capture(raw_exporter=raw) as exporter:
            application = create_app()
            session = ChatSession(user_id=1, conversation_id=1, account={"id": 1})
            application.dependency_overrides[session_for] = lambda: ("request-test", session)
            agent = create_deep_agent(model=FakeToolsChatModel(responses=["Hello!"]), system_prompt="A test")
            with patch("app.main.repository.initialize"), patch("app.main.dispose_engine"), TestClient(application) as client, patch("app.services.chat.ensure_active"), patch(
                "app.services.chat.repository.messages", return_value=[]
            ), patch("app.services.chat.repository.conversations", return_value=[]), patch(
                "app.services.chat.quota.check_limit"
            ), patch("app.services.chat.quota.resets_at", return_value=None), patch(
                "app.services.chat.quota.upload_resets_at", return_value=None
            ), patch("app.services.chat.quota.record"), patch(
                "app.services.chat.repository.save_turn"
            ), patch("app.services.chat.name_conversation"), patch(
                "app.services.chat.make_agent", return_value=agent
            ):
                for path in ["/health", "/api/state", "/docs", "/static/a.js"]:
                    response = client.get(path)
                    self.assertEqual(response.status_code, 404 if path.startswith("/static") else 200)
                trace.flush_traces()
                self.assertEqual(exporter.get_finished_spans(), ())
                self.assertEqual(raw.get_finished_spans(), ())
                response = client.post("/api/chat", json={"message": "Hi"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["answer"], "Hello!")
                trace.flush_traces()
                spans = exporter.get_finished_spans()
                self.assert_nested(spans)
                self.assertEqual(len({s.context.trace_id for s in spans}), 1)
                self.assertEqual([s.name for s in spans if s.attributes.get("langfuse.observation.type") == "generation"],
                                 ["generate-response"])
                self.assertTrue(all(s.instrumentation_scope.name == "langfuse-sdk" for s in raw.get_finished_spans()))

    def test_http_tracing_stays_disabled_with_custom_exclusions(self):
        raw = InMemorySpanExporter()
        with self.capture(raw_exporter=raw), patch.dict(os.environ, {"LANGFUSE_EXCLUDED_ROUTES": "/api/state"}):
            with patch("app.main.repository.initialize"), patch("app.main.dispose_engine"), TestClient(create_app()) as client:
                self.assertEqual(client.get("/health").status_code, 200)
                self.assertEqual(client.get("/api/state").status_code, 401)
            self.assertEqual(raw.get_finished_spans(), ())

    def test_client_configures_filter_and_redaction(self):
        with patch.object(trace, "_client", None), patch.object(trace, "Langfuse") as factory:
            self.assertIs(trace.get_tracing_client(), factory.return_value)
            self.assertIs(trace.get_tracing_client(), factory.return_value)
        factory.assert_called_once_with(
            mask_otel_spans=trace.mask_otel_spans, should_export_span=trace.export_chat_span, timeout=60,
        )

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
        }), patch('app.core.trace.get_tracing_client', return_value=client):
            with self.assertRaisesRegex(ValueError, "Private failure detail"):
                with trace.trace_chat_turn(
                    session_id="test-session", question="Private question",
                    model="fake", has_document=False,
                ):
                    raise ValueError("Private failure detail")
        span.update.assert_called_once_with(level="ERROR", status_message="Chat turn failed")

    def test_agent_trace_is_nested_and_content_redacted(self):
        with self.capture() as exporter:
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
        generations = [s for s in spans if s.attributes.get("langfuse.observation.type") == "generation"]
        self.assertEqual([s.name for s in generations], ["generate-response"])
        self.assertFalse(trace.INTERNAL_STEPS.intersection(s.name for s in spans))
        self.assertIn("LangGraph", [s.name for s in spans])
        self.assertIn("model", [s.name for s in spans])
        self.assert_nested(spans)
        self.assertTrue(all(
            "Top secret" not in str(s.attributes)
            and "The answer is 42" not in str(s.attributes) for s in spans
        ))

    def test_tool_trace_keeps_each_generation_tool_result_and_usage(self):
        tool = StructuredTool.from_function(
            func=lambda query: "Matched document page 2", name="search_documents",
            description="Search the test document",
        )
        model = FakeToolCallModel(responses=[
            AIMessage(content="", tool_calls=[{
                "name": "search_documents", "args": {"query": "answer"}, "id": "call-test",
            }], usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}),
            AIMessage(content="The answer is 42.", usage_metadata={
                "input_tokens": 20, "output_tokens": 5, "total_tokens": 25,
            }),
        ])
        with self.capture(content="true") as exporter:
            agent = create_deep_agent(model=model, tools=[tool], system_prompt="A test")
            with trace.trace_chat_turn(
                session_id="tool-session", question="Find the answer", model="fake", has_document=True,
            ) as (handler, span):
                result = agent.invoke({"messages": [{"role": "user", "content": "Find the answer"}]},
                                      config={"callbacks": [handler]})
                span.update(output=result["messages"][-1].content)
        spans = exporter.get_finished_spans()
        self.assert_nested(spans)
        self.assertFalse(trace.INTERNAL_STEPS.intersection(s.name for s in spans))
        generations = [s for s in spans if s.attributes.get("langfuse.observation.type") == "generation"]
        self.assertEqual([s.name for s in generations], ["generate-response", "generate-response"])
        self.assertEqual(sum(json.loads(s.attributes["langfuse.observation.usage_details"])["input"]
                             for s in generations), 30)
        tools = [s for s in spans if s.attributes.get("langfuse.observation.type") == "tool"]
        self.assertEqual([s.name for s in tools], ["search_documents"])
        self.assertIn("Matched document page 2", str(tools[0].attributes))
        root = next(s for s in spans if s.name == "chat-response")
        self.assertIn("Find the answer", str(root.attributes))
        self.assertIn("The answer is 42.", str(root.attributes))

    def test_streamed_generations_are_named_and_nested(self):
        with self.capture() as exporter:
            agent = create_deep_agent(model=FakeToolsChatModel(responses=["Hello"]), system_prompt="A test")
            with trace.trace_chat_turn(
                session_id="stream-session", question="Hi", model="fake", has_document=False,
            ) as (handler, span):
                list(agent.stream({"messages": [{"role": "user", "content": "Hi"}]},
                                  config={"callbacks": [handler]}))
                span.update(output="Hello")
        spans = exporter.get_finished_spans()
        self.assert_nested(spans)
        self.assertFalse(trace.INTERNAL_STEPS.intersection(s.name for s in spans))
        self.assertEqual([s.name for s in spans if s.attributes.get("langfuse.observation.type") == "generation"],
                         ["generate-response"])


if __name__ == "__main__":
    unittest.main()
