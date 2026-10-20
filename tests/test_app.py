import unittest
from unittest.mock import patch

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
        session = ChatSession(uploads={item.id: item})
        self.app.dependency_overrides[session_for] = lambda: ("test-session", session)
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["uploads"][0]["filename"], "isolated.txt")
        self.assertEqual(sessions, {})
        self.assertNotIn("set-cookie", response.headers)

    def test_session_cookie_is_reused_and_private(self):
        first = self.client.get("/api/state")
        cookie = first.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        token = self.client.cookies[COOKIE]
        self.client.get("/api/state")
        self.assertEqual(self.client.cookies[COOKIE], token)
        self.assertEqual(len(sessions), 1)

    def test_expired_session_is_replaced(self):
        self.client.get("/api/state")
        token = self.client.cookies[COOKIE]
        sessions[token].touched -= SESSION_TTL + 1
        self.client.get("/api/state")
        self.assertNotIn(token, sessions)
        self.assertNotEqual(self.client.cookies[COOKIE], token)

    def test_session_capacity_returns_service_unavailable(self):
        with patch("app.dependencies.MAX_SESSIONS", 0):
            response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(sessions, {})

    def test_service_errors_keep_http_contract(self):
        for path, body, status, detail in (
            ("/api/chat", {"message": "  "}, 422, "Message cannot be blank"),
            ("/api/chat", {"message": "Hello"}, 400, "Select a user before chatting"),
            ("/api/users", {"name": "  "}, 422, "Name cannot be blank"),
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

    def test_lifespan_flushes_after_failure(self):
        with patch("app.db.repository.initialize"), patch("app.main.flush_traces") as flush:
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                with TestClient(self.app):
                    raise RuntimeError("test failure")
            flush.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
