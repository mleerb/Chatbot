import json
import os
import threading
import unittest
from contextlib import nullcontext
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, AIMessageChunk

from app.main import app
from app.services import chat, guest
from app.services.agent import stream_answer
from app.services.sessions import sessions
from app.services.steps import step_label
from tests.fake_database import mock_database


def text(value, node="model"):
    return "messages", (AIMessageChunk(content=value), {"langgraph_node": node})


def model_update(message):
    return "updates", {"model": {"messages": [message]}}


def tool_turn(*calls):
    return model_update(AIMessage(content="", tool_calls=[
        {"name": name, "args": args, "id": f"call-{index}"} for index, (name, args) in enumerate(calls)
    ], usage_metadata={"input_tokens": 5, "output_tokens": 5, "total_tokens": 10}))


def final_turn(content):
    return model_update(AIMessage(content=content, usage_metadata={
        "input_tokens": 7, "output_tokens": 3, "total_tokens": 10}))


SCRIPT = [
    text("Let me "), text("check."), tool_turn(("search_current_question", {})),
    text("ignored", node="tools"), text("The "), text("answer."), final_turn("The answer."),
]


def fake_agent(script, before=None):
    agent = Mock()

    def stream(*args, **kwargs):
        for index, item in enumerate(script):
            if before:
                before(index)
            yield item

    agent.stream.side_effect = stream
    return agent


def events(response):
    return [json.loads(line[len("data: "):]) for line in response.text.splitlines() if line.startswith("data: ")]


class StreamAnswerTests(unittest.TestCase):
    def run_stream(self, script, stop=None, before=None):
        usage = []
        with patch("app.services.agent.conversation_messages", return_value=[]):
            items = list(stream_answer(fake_agent(script, before), "Question", [], "guest", trace=False,
                                       usage=usage, stop=stop))
        return items, usage

    def test_streams_model_text_and_tool_steps_then_the_final_answer(self):
        items, usage = self.run_stream(SCRIPT)
        self.assertEqual(items, [
            {"type": "text", "text": "Let me "}, {"type": "text", "text": "check."},
            {"type": "step", "label": "Searching the web"},
            {"type": "text", "text": "The "}, {"type": "text", "text": "answer."},
            {"type": "end", "answer": "The answer.", "stopped": False},
        ])
        self.assertEqual(usage, [20])

    def test_stop_keeps_the_text_written_since_the_last_step(self):
        stop = threading.Event()
        items, usage = self.run_stream(SCRIPT, stop, before=lambda index: index == 5 and stop.set())
        self.assertEqual(items[-1], {"type": "end", "answer": "The", "stopped": True})
        self.assertEqual(usage, [10])

    def test_empty_answer_without_stop_fails(self):
        with self.assertRaises(ValueError):
            self.run_stream([final_turn("")])

    def test_step_labels_name_the_file_or_action(self):
        files = {"a1": "report.docx"}
        self.assertEqual(step_label({"name": "read_page", "args": {"page": 2, "file_id": "a1"}}, files),
                         "Reading report.docx")
        self.assertEqual(step_label({"name": "edit_uploaded_file", "args": {}}, files), "Editing report.docx")
        self.assertEqual(step_label({"name": "search_in_file", "args": {}}, {"a": "x", "b": "y"}),
                         "Searching your file")
        self.assertEqual(step_label({"name": "create_text_file", "args": {"filename": "plan.pdf"}}, {}),
                         "Creating plan.pdf")
        self.assertEqual(step_label({"name": "generate_image", "args": {}}, {}), "Creating an image")
        self.assertEqual(step_label({"name": "ls", "args": {}}, {}), "Working")


class StreamEndpointTests(unittest.TestCase):
    def setUp(self):
        tracing = patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "", "LANGFUSE_BASE_URL": ""})
        tracing.start()
        self.addCleanup(tracing.stop)
        sessions.clear()
        guest.meters.clear()
        self.addCleanup(guest.meters.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(sessions.clear)
        self.database = mock_database(self)
        title = patch("app.services.title.generate", return_value="")
        title.start()
        self.addCleanup(title.stop)

    def stream(self, script, message="Question", before=None, **payload):
        with patch("app.services.chat.make_agent", return_value=fake_agent(script, before)):
            return self.client.post("/api/chat/stream", json={"message": message, **payload})

    def test_account_stream_sends_events_and_saves_the_turn(self):
        response = self.stream(SCRIPT)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        self.assertIn("no-transform", response.headers["cache-control"])
        items = events(response)
        self.assertEqual([item["type"] for item in items], ["text", "text", "step", "text", "text", "done"])
        self.assertEqual(items[-1]["display_answer"], "The answer.")
        self.assertFalse(items[-1]["stopped"])
        messages = self.client.get("/api/state").json()["messages"]
        self.assertEqual([item["content"] for item in messages], ["Question", "The answer."])
        self.assertEqual(self.database.usages[1]["tokens"], 20)

    def test_stop_endpoint_ends_the_turn_and_keeps_partial_text(self):
        def before(index):
            if index == 5:
                self.assertEqual(self.client.post("/api/chat/stop").json(), {"stopped": True})

        items = events(self.stream(SCRIPT, before=before))
        self.assertEqual(items[-1]["type"], "done")
        self.assertTrue(items[-1]["stopped"])
        self.assertEqual(items[-1]["display_answer"], "The")
        answer = self.client.get("/api/state").json()["messages"][-1]
        self.assertEqual((answer["content"], answer["stopped"]), ("The", True))
        self.assertEqual(self.client.post("/api/chat/stop").json(), {"stopped": False})

    def test_closing_the_stream_stops_the_turn(self):
        token, session = next(iter(sessions.items()))
        release = threading.Event()
        agent = fake_agent(SCRIPT, before=lambda index: index == 2 and release.wait(5))
        with patch("app.services.chat.make_agent", return_value=agent):
            events_iter = chat.stream_reply(token, session, "Question")
            self.assertEqual(next(events_iter), {"type": "text", "text": "Let me "})
            events_iter.close()
            release.set()
            self.assertTrue(session.lock.acquire(timeout=5))
            session.lock.release()
        answer = self.database.turns[1][-1]
        self.assertTrue(answer["stopped"])
        self.assertIsNone(session.stopping)

    def test_failures_before_and_during_the_stream(self):
        self.assertEqual(self.client.post("/api/chat/stream", json={"message": "   "}).status_code, 422)
        with patch("app.services.chat.make_agent", side_effect=RuntimeError("down")):
            items = events(self.client.post("/api/chat/stream", json={"message": "Question"}))
        self.assertEqual(items, [{"type": "error", "status": 502,
                                  "detail": "Could not get an answer. Check the server log and model settings."}])
        self.assertEqual(self.client.get("/api/state").json()["messages"], [])
        self.stream(SCRIPT)
        with patch("app.services.quota.USER_TOKEN_LIMIT", 20):
            self.assertEqual(self.client.post("/api/chat/stream", json={"message": "Question"}).status_code, 403)

    def traced(self):
        calls = []

        def record(**kwargs):
            calls.append(kwargs)
            return nullcontext((None, None))

        return calls, patch("app.services.agent.trace_chat_turn", side_effect=record)

    def test_account_trace_uses_random_session_id_not_login_cookie(self):
        calls, tracer = self.traced()
        with tracer:
            events(self.stream(SCRIPT))
        cookies = set(self.client.cookies.values())
        self.assertTrue(cookies)
        self.assertRegex(calls[0]["session_id"], r"^s-[0-9a-f]{8}$")
        self.assertFalse(cookies & {str(value) for value in calls[0].values()})
        self.assertFalse(calls[0]["guest"])

    def test_guest_stream_is_traced_when_enabled_without_guest_token(self):
        self.client.post("/api/auth/logout")
        token = self.client.post("/api/auth/guest").json()["guest_token"]
        self.client.headers["x-guest-session"] = token
        calls, tracer = self.traced()
        with patch.dict(os.environ, {"LANGFUSE_TRACE_GUESTS": "true"}), tracer, patch(
            "app.db.repository.save_turn"
        ) as save:
            events(self.stream(SCRIPT))
        save.assert_not_called()
        self.assertTrue(calls[0]["guest"])
        self.assertRegex(calls[0]["session_id"], r"^s-[0-9a-f]{8}$")
        self.assertNotIn(token, [str(value) for value in calls[0].values()])

    def test_guest_stream_is_not_traced_or_stored(self):
        self.client.post("/api/auth/logout")
        token = self.client.post("/api/auth/guest").json()["guest_token"]
        self.client.headers["x-guest-session"] = token
        with patch.dict(os.environ, {"LANGFUSE_TRACE_GUESTS": "false"}), patch(
            "app.services.agent.trace_chat_turn"
        ) as trace, patch("app.db.repository.save_turn") as save:
            items = events(self.stream(SCRIPT))
        trace.assert_not_called()
        save.assert_not_called()
        self.assertEqual(items[-1]["display_answer"], "The answer.")
        self.assertEqual(len(self.client.get("/api/state").json()["messages"]), 2)

    def test_stream_steps_use_upload_names(self):
        upload = self.client.post("/api/document", files={"file": ("notes.txt", b"hello")}).json()
        script = [tool_turn(("get_outline", {"file_id": upload["id"]})), final_turn("Done")]
        items = events(self.stream(script))
        self.assertEqual(items[0], {"type": "step", "label": "Reading notes.txt"})


if __name__ == "__main__":
    unittest.main()
