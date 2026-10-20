import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.dependencies import session_for
from app.main import create_app
from app.services.sessions import COOKIE, SESSION_TTL, ChatSession, Upload, sessions


class AppTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.addCleanup(sessions.clear)
        self.app = create_app()
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def test_backend_health_and_documentation(self):
        for path in ("/health", "/docs", "/openapi.json"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get('/health').json(), {'status': 'ok'})
        for path in ('/', '/static/chat.js'):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_api_paths_and_schemas(self):
        schema = self.client.get("/openapi.json").json()
        self.assertEqual(set(schema["paths"]), {
            "/api/auth/me", "/api/auth/login", "/api/auth/register", "/api/auth/logout", "/api/auth/guest", "/api/auth/guest/close",
            "/api/state", "/api/chat", "/api/document", "/api/document/download",
            "/api/document/edited", "/api/users", "/api/users/{user_id}/select",
            "/api/users/{user_id}/messages", "/api/files/download", "/api/conversations",
            "/api/conversations/{conversation_id}", "/api/conversations/{conversation_id}/select",
        })
        chat = schema["paths"]["/api/chat"]["post"]
        self.assertEqual(chat["responses"]["200"]["content"]["application/json"]["schema"],
                         {"$ref": "#/components/schemas/ChatResponse"})
        self.assertIn("ChatRequest", schema["components"]["schemas"])
        self.assertIn("UserRequest", schema["components"]["schemas"])

    def test_session_dependency_can_be_overridden(self):
        item = Upload("isolated.txt", b"", "", "", "Ready")
        session = ChatSession(account={"id": 1, "name": "Test", "email": "test@example.com"}, uploads={item.id: item})
        self.app.dependency_overrides[session_for] = lambda: ("test-session", session)
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["uploads"][0]["filename"], "isolated.txt")
        self.assertEqual(sessions, {})
        self.assertNotIn("set-cookie", response.headers)

    def test_session_cookie_is_reused_and_private(self):
        first = self.client.get("/api/auth/me")
        cookie = first.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        token = self.client.cookies[COOKIE]
        self.client.get("/api/auth/me")
        self.assertEqual(self.client.cookies[COOKIE], token)
        self.assertEqual(len(sessions), 1)

    def test_expired_session_is_replaced(self):
        self.client.get("/api/auth/me")
        token = self.client.cookies[COOKIE]
        sessions[token].touched -= SESSION_TTL + 1
        self.client.get("/api/auth/me")
        self.assertNotIn(token, sessions)
        self.assertNotEqual(self.client.cookies[COOKIE], token)

    def test_session_clear_releases_state_and_cancels_pending_close(self):
        timer = Mock()
        item = Upload("temporary.txt", b"private", "private", "", "Ready")
        session = ChatSession(
            user_id=1, account={"id": 1}, guest=True, close_timer=timer,
            conversation_id=2, guest_conversation={"id": 2},
            history=[{"content": "private"}], guest_messages=[{"content": "private"}],
            uploads={item.id: item}, generated={"temporary": Mock()},
        )
        session.clear()
        session.clear()
        timer.cancel.assert_called_once_with()
        self.assertIsNone(session.close_timer)
        self.assertIsNone(session.user_id)
        self.assertIsNone(session.account)
        self.assertFalse(session.guest)
        self.assertIsNone(session.conversation_id)
        self.assertIsNone(session.guest_conversation)
        self.assertEqual(session.history, [])
        self.assertEqual(session.guest_messages, [])
        self.assertEqual(session.file_state(), {"uploads": [], "generated_files": []})

    def test_session_capacity_returns_service_unavailable(self):
        with patch("app.dependencies.MAX_SESSIONS", 0):
            response = self.client.get("/api/auth/me")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(sessions, {})

    def test_service_errors_keep_http_contract(self):
        for path, body, status, detail in (
            ("/api/chat", {"message": "  "}, 401, "Log in or continue as guest"),
            ("/api/chat", {"message": "Hello"}, 401, "Log in or continue as guest"),
            ("/api/users", {"name": "  "}, 401, "Log in to continue"),
        ):
            with self.subTest(path=path, body=body):
                response = self.client.post(path, json=body)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.json(), {"detail": detail})

    def test_lifespan_initializes_database_and_flushes_traces(self):
        with patch("app.db.repository.initialize") as initialize, patch("app.main.flush_traces") as flush:
            with TestClient(self.app) as client:
                initialize.assert_called_once_with()
                self.assertEqual(client.get("/health").status_code, 200)
                flush.assert_not_called()
            flush.assert_called_once_with()

    def test_lifespan_disposes_engine_after_shutdown(self):
        with patch("app.db.repository.initialize"), patch("app.main.flush_traces"), patch(
            "app.main.dispose_engine"
        ) as dispose:
            with TestClient(self.app):
                dispose.assert_not_called()
            dispose.assert_called_once_with()

    def test_lifespan_cleans_up_when_initialization_fails(self):
        with patch("app.db.repository.initialize", side_effect=RuntimeError("startup failed")), patch(
            "app.main.flush_traces"
        ) as flush, patch("app.main.dispose_engine") as dispose:
            with self.assertRaisesRegex(RuntimeError, "startup failed"):
                with TestClient(self.app):
                    pass
            flush.assert_called_once_with()
            dispose.assert_called_once_with()

    def test_lifespan_disposes_engine_even_if_trace_flush_fails(self):
        with patch("app.db.repository.initialize"), patch(
            "app.main.flush_traces", side_effect=RuntimeError("flush failed")
        ), patch("app.main.dispose_engine") as dispose:
            with self.assertRaisesRegex(RuntimeError, "flush failed"):
                with TestClient(self.app):
                    pass
            dispose.assert_called_once_with()

    def test_lifespan_flushes_after_failure(self):
        with patch("app.db.repository.initialize"), patch("app.main.flush_traces") as flush:
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                with TestClient(self.app):
                    raise RuntimeError("test failure")
            flush.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
