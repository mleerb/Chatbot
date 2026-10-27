import os
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.core import trace
from app.main import app
from app.services import guest
from app.services.sessions import sessions
from tests.fake_database import mock_database


class AnswerControlTests(unittest.TestCase):
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

    def send(self, message, replace_from=None, answer=None, trace_id=None):
        def reply(agent, question, history, *args, traces, **kwargs):
            if trace_id:
                traces.append(trace_id)
            self.history = history
            return answer or f"Answer to {question}"

        payload = {"message": message} if replace_from is None else {"message": message, "replace_from": replace_from}
        with patch("app.services.chat.make_agent"), patch("app.services.chat.answer_question", side_effect=reply):
            return self.client.post("/api/chat", json=payload)

    def contents(self):
        return [item["content"] for item in self.client.get("/api/state").json()["messages"]]

    def start_guest(self):
        self.client.post("/api/auth/logout")
        self.client.headers["x-guest-session"] = self.client.post("/api/auth/guest").json()["guest_token"]

    def check_edit_and_regenerate(self):
        self.send("First")
        self.send("Second")
        self.assertEqual(self.send("Second", replace_from=2, answer="New answer").status_code, 200)
        self.assertEqual(self.contents(), ["First", "Answer to First", "Second", "New answer"])
        self.assertEqual([item["content"] for item in self.history], ["First", "Answer to First"])
        self.assertEqual(self.send("Changed first", replace_from=0).status_code, 200)
        self.assertEqual(self.contents(), ["Changed first", "Answer to Changed first"])
        self.assertEqual(self.history, [])
        for index in (1, 2, 9):
            response = self.send("Nope", replace_from=index)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.json()["detail"], "Message not found")
        self.assertEqual(self.contents(), ["Changed first", "Answer to Changed first"])
        self.assertEqual(self.send("Bad", replace_from=-1).status_code, 422)

    def test_account_edit_and_regenerate_replace_later_messages(self):
        self.check_edit_and_regenerate()

    def test_guest_edit_and_regenerate_replace_later_messages(self):
        self.start_guest()
        with patch("app.db.repository.save_turn", side_effect=AssertionError("Guest database access")):
            self.check_edit_and_regenerate()

    def test_edited_question_keeps_its_files(self):
        upload = self.client.post("/api/document", files={"file": ("notes.txt", b"hello")}).json()
        self.send("Read this")
        self.send("Read this carefully", replace_from=0)
        messages = self.client.get("/api/state").json()["messages"]
        self.assertEqual(messages[0]["attachments"], [{"id": upload["id"], "filename": "notes.txt"}])

    def test_failed_regenerate_keeps_the_old_answer(self):
        self.send("Question")
        with patch("app.services.chat.make_agent", side_effect=RuntimeError("down")):
            self.assertEqual(self.client.post("/api/chat", json={"message": "Question", "replace_from": 0}).status_code, 502)
        self.assertEqual(self.contents(), ["Question", "Answer to Question"])

    def test_edit_needs_an_open_conversation(self):
        self.client.delete(f"/api/conversations/{self.client.get('/api/state').json()['conversation_id']}")
        self.assertEqual(self.send("Hello", replace_from=0).status_code, 404)

    def test_account_rating_is_saved_and_scored(self):
        self.send("Question", trace_id="trace-9")
        with patch("app.services.chat.score_answer") as score:
            response = self.client.post("/api/chat/rating", json={"index": 1, "rating": "up"})
            self.assertEqual(response.json(), {"rating": "up"})
            score.assert_called_once_with("trace-9", "up")
            self.client.post("/api/chat/rating", json={"index": 1, "rating": None})
            score.assert_called_with("trace-9", None)
        self.assertIsNone(self.client.get("/api/state").json()["messages"][1]["rating"])
        self.client.post("/api/chat/rating", json={"index": 1, "rating": "down"})
        self.assertEqual(self.client.get("/api/state").json()["messages"][1]["rating"], "down")
        self.assertEqual(self.client.post("/api/chat/rating", json={"index": 0, "rating": "up"}).status_code, 404)
        self.assertEqual(self.client.post("/api/chat/rating", json={"index": 1, "rating": "meh"}).status_code, 422)

    def test_untraced_and_guest_ratings_are_not_scored(self):
        self.send("Question")
        with patch("app.services.chat.score_answer") as score:
            self.assertEqual(self.client.post("/api/chat/rating", json={"index": 1, "rating": "up"}).status_code, 200)
            self.start_guest()
            self.send("Guest question")
            self.assertEqual(self.client.post("/api/chat/rating", json={"index": 1, "rating": "down"}).status_code, 200)
            self.assertEqual(self.client.post("/api/chat/rating", json={"index": 2, "rating": "down"}).status_code, 404)
        score.assert_not_called()
        self.assertEqual(self.client.get("/api/state").json()["messages"][1]["rating"], "down")


class ScoreTests(unittest.TestCase):
    def test_score_is_skipped_without_tracing(self):
        with patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": ""}), patch("app.core.trace.get_tracing_client") as client:
            trace.score_answer("trace-1", "up")
        client.assert_not_called()

    def test_score_uses_one_upserted_value_per_answer(self):
        keys = {"LANGFUSE_PUBLIC_KEY": "pk", "LANGFUSE_SECRET_KEY": "sk", "LANGFUSE_BASE_URL": "http://localhost"}
        client = Mock()
        with patch.dict(os.environ, keys), patch("app.core.trace.get_tracing_client", return_value=client):
            for rating in ("up", "down", None):
                trace.score_answer("trace-1", rating)
            client.create_score.side_effect = RuntimeError("offline")
            trace.score_answer("trace-1", "up")
        self.assertEqual([item.kwargs["value"] for item in client.create_score.call_args_list], [1, -1, 0, 1])
        self.assertEqual({item.kwargs["score_id"] for item in client.create_score.call_args_list}, {"trace-1-feedback"})
        self.assertEqual(client.create_score.call_args.kwargs["trace_id"], "trace-1")


if __name__ == "__main__":
    unittest.main()
