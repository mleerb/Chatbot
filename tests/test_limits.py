import asyncio
import os
import unittest
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from app.core import limits
from app.core.errors import ServiceError
from app.main import app
from app.routers.documents import upload_document
from app.services.sessions import ChatSession, sessions
from tests.fake_database import mock_database


class UploadLimitTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.addCleanup(sessions.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.database = mock_database(self)
        settings = patch.dict(os.environ, {
            "UPLOAD_MAX_MB": "1", "CONVERSATION_MAX_FILES": "2", "CONVERSATION_MAX_UPLOAD_MB": "2",
            "LLAMA_CLOUD_API_KEY": "", "EMBEDDING_MODEL": "", "WORKSPACE_EXPORT_ENABLED": "false",
        })
        settings.start()
        self.addCleanup(settings.stop)

    def upload(self, data=b"text"):
        return self.client.post("/api/document", files={"file": ("test.txt", data)})

    def test_authenticated_upload_settings_expose_configuration_not_credentials(self):
        response = self.client.get("/api/document/settings")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["max_file_bytes"], limits.MIB)
        self.assertEqual(result["max_conversation_files"], 2)
        self.assertFalse(result["parsing_enabled"])
        self.assertFalse(result["guest_inspection_enabled"])
        self.assertIn(".txt", result["text_extensions"])
        self.assertNotIn("API_KEY", response.text)
        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/document/settings").status_code, 401)
        token = self.client.post("/api/auth/guest").json()["guest_token"]
        self.client.headers["x-guest-session"] = token
        with patch.dict(os.environ, {"WORKSPACE_EXPORT_ENABLED": "true", "WORKSPACE_EXPORT_GUESTS": "true",
                                     "LLAMA_CLOUD_API_KEY": "private-key"}):
            result = self.client.get("/api/document/settings").json()
        self.assertTrue(result["guest_inspection_enabled"])
        self.assertTrue(result["parsing_enabled"])
        self.assertNotIn("private-key", str(result))

    def test_exact_size_allowed_and_oversize_rejected_before_extraction(self):
        self.assertEqual(self.upload(b"a" * limits.MIB).status_code, 200)
        with patch("app.services.documents.upload_context") as extract:
            response = self.upload(b"a" * (limits.MIB + 1))
        self.assertEqual(response.status_code, 413)
        self.assertIn("1 MiB", response.json()["detail"])
        extract.assert_not_called()
        self.assertEqual(len(self.database.files), 1)
        self.assertEqual(len(self.client.get("/api/state").json()["uploads"]), 1)

    def test_bounded_read_checks_missing_size_and_closes_upload(self):
        file = Mock(filename="test.txt", size=None)
        file.read = AsyncMock(return_value=b"x" * (limits.MIB + 1))
        file.close = AsyncMock()
        with self.assertRaises(ServiceError) as raised:
            asyncio.run(upload_document(("token", ChatSession()), file))
        self.assertEqual(raised.exception.status_code, 413)
        file.read.assert_awaited_once_with(limits.MIB + 1)
        file.close.assert_awaited_once()

    def test_account_file_limit_and_existing_downloads_preserved(self):
        first = self.upload(b"first").json()
        self.assertEqual(self.upload(b"second").status_code, 200)
        with patch("app.services.documents.upload_context") as extract:
            rejected = self.upload(b"third")
        self.assertEqual(rejected.status_code, 409)
        self.assertIn("file limit", rejected.json()["detail"])
        extract.assert_not_called()
        self.assertEqual(len(self.database.files), 2)
        self.assertEqual(self.client.get("/api/document/download", params={"file_id": first["id"]}).content, b"first")
        self.client.delete("/api/document", params={"file_id": first["id"]})
        self.assertEqual(self.upload(b"new").status_code, 200)

    def test_lowering_limits_never_deletes_existing_files(self):
        first = self.upload(b"existing").json()
        with patch.dict(os.environ, {"CONVERSATION_MAX_FILES": "1"}):
            self.assertEqual(self.upload().status_code, 409)
            self.assertEqual(self.client.get("/api/document/download", params={"file_id": first["id"]}).content, b"existing")
        self.assertEqual(len(self.database.files), 1)

    def test_total_budget_checks_database_not_stale_session_and_excludes_generated(self):
        state = self.client.get("/api/state").json()
        uid, cid = state["user_id"], state["conversation_id"]
        with patch.dict(os.environ, {"UPLOAD_MAX_MB": "3"}):
            self.database.save_file(uid, cid, "upload", "external", "external.txt", b"x" * (2 * limits.MIB))
        self.database.save_file(uid, cid, "generated", "generated", "out.txt", b"x" * 10)
        with patch("app.services.documents.upload_context") as extract:
            response = self.upload(b"x")
        self.assertEqual(response.status_code, 409)
        self.assertIn("storage limit", response.json()["detail"])
        extract.assert_not_called()
        self.assertIn("external", self.database.files)
        self.assertIn("generated", self.database.files)

    def test_capacity_rechecked_after_parsing_and_service_error_not_masked(self):
        with patch("app.services.documents.repository.check_upload_capacity", side_effect=[None, ServiceError(409, "limit")]):
            self.assertEqual(self.upload().status_code, 409)
        with patch("app.services.documents.storage.save_upload", side_effect=ServiceError(409, "limit")):
            self.assertEqual(self.upload().status_code, 409)
        self.assertEqual(self.database.files, {})

    def test_guest_limit_is_memory_only_and_new_chat_has_fresh_capacity(self):
        self.client.post("/api/auth/logout")
        token = self.client.post("/api/auth/guest").json()["guest_token"]
        self.client.headers["x-guest-session"] = token
        with patch("app.db.repository.check_upload_capacity", side_effect=AssertionError("Guest DB access")):
            self.assertEqual(self.upload(b"one").status_code, 200)
            self.assertEqual(self.upload(b"two").status_code, 200)
            self.assertEqual(self.upload(b"three").status_code, 409)
            self.assertEqual(len(self.client.get("/api/state").json()["uploads"]), 2)
            self.client.post("/api/conversations")
            self.assertEqual(self.upload(b"new").status_code, 200)

    def test_chat_timeout_reports_504_without_losing_upload(self):
        item = self.upload().json()
        with patch("app.services.chat.make_agent", side_effect=TimeoutError("private provider failure")):
            response = self.client.post("/api/chat", json={"message": "Hi"})
        self.assertEqual(response.status_code, 504)
        self.assertIn("timed out", response.json()["detail"])
        self.assertNotIn("private provider failure", response.text)
        self.assertEqual(self.client.get("/api/document/download", params={"file_id": item["id"]}).status_code, 200)


class TimeoutSettingsTests(unittest.TestCase):
    def test_defaults_and_invalid_settings(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(limits.upload_limits(), (20 * limits.MIB, 20, 100 * limits.MIB))
            limits.validate()
            self.assertEqual(limits.timeout("CHAT_TIMEOUT_SECONDS"), 180)
            self.assertEqual(limits.timeout("PARSE_TIMEOUT_SECONDS"), 600)
        for value in ["0", "-1", "nan", "inf", "abc", ""]:
            with self.subTest(value=value), patch.dict(os.environ, {"CHAT_TIMEOUT_SECONDS": value}):
                with self.assertRaises(ValueError):
                    limits.validate()
        with patch.dict(os.environ, {"UPLOAD_MAX_MB": "1.5"}):
            with self.assertRaises(ValueError):
                limits.upload_limits()

    def test_chat_gateway_and_provider_initialization_receive_timeouts(self):
        from app.services.model import chat_model

        with patch.dict(os.environ, {"CHAT_MODEL": "openai:test", "OPENAI_API_KEY": "test",
                                     "OPENAI_BASE_URL": "https://example.com", "CHAT_TIMEOUT_SECONDS": "247"}), patch(
            "app.services.model.ChatOpenAI"
        ) as factory:
            chat_model()
            self.assertEqual(factory.call_args.kwargs["timeout"], 247)
            self.assertEqual(factory.call_args.kwargs["max_retries"], 1)
        with patch.dict(os.environ, {"CHAT_MODEL": "openai:test", "OPENAI_API_KEY": "test",
                                     "OPENAI_BASE_URL": "", "TITLE_TIMEOUT_SECONDS": "121"}), patch(
            "app.services.model.init_chat_model"
        ) as factory:
            chat_model("TITLE_TIMEOUT_SECONDS")
            factory.assert_called_once_with("openai:test", timeout=121, max_retries=1)

    def test_parse_request_and_polling_timeouts_are_configurable(self):
        from app.services import parse

        client = Mock()
        client.parsing.parse.return_value.markdown.pages = []
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "test", "PARSE_REQUEST_TIMEOUT_SECONDS": "125",
                                     "PARSE_TIMEOUT_SECONDS": "900"}), patch(
            "app.services.parse.LlamaCloud", return_value=client
        ) as factory:
            parse.parse_file("test.txt", b"text")
        self.assertEqual(factory.call_args.kwargs["timeout"], 125)
        self.assertEqual(client.parsing.parse.call_args.kwargs["timeout"], 900)

    def test_parser_timeout_falls_back_without_losing_local_text(self):
        from app.services import parse
        from app.services.extract import upload_context

        with patch("app.services.extract.parse.enabled", return_value=True), patch(
            "app.services.extract.parse.parse_file", side_effect=parse.PollingTimeoutError("private detail")
        ):
            inspection = {}
            text, _, status, chunks = upload_context("file.txt", b"kept text", inspection=inspection)
        self.assertEqual(text, "kept text")
        self.assertEqual(chunks[0].text, "kept text")
        self.assertIn("timed out", status)
        self.assertNotIn("private detail", status)
        self.assertEqual(inspection["parse_result"], "timeout_local_fallback")

    def test_embedding_timeout_configuration(self):
        from app.services import embed

        response = Mock()
        response.data = [Mock(index=0, embedding=[1.0] * 512)]
        with patch.dict(os.environ, {"EMBEDDING_TIMEOUT_SECONDS": "123"}), patch(
            "app.services.embed.OpenAI"
        ) as factory:
            factory.return_value.__enter__.return_value.embeddings.create.return_value = response
            embed.request(["synthetic text"], ("fake", ""))
        self.assertEqual(factory.call_args.kwargs["timeout"], 123)

    def test_search_and_image_clients_use_configurable_timeouts(self):
        from app.services.images import client
        from app.tools.search import search_web

        with patch.dict(os.environ, {"TAVILY_API_KEY": "test", "SEARCH_TIMEOUT_SECONDS": "80"}), patch(
            "app.tools.search.httpx.Client"
        ) as factory:
            factory.return_value.__enter__.return_value.post.return_value.json.return_value = {"results": []}
            search_web("test")
            factory.assert_called_once_with(timeout=80)
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test", "OPENAI_BASE_URL": "https://example.com",
                                     "IMAGE_TIMEOUT_SECONDS": "360"}), patch("app.services.images.OpenAI") as factory:
            client()
            self.assertEqual(factory.call_args.kwargs["timeout"], 360)


if __name__ == "__main__":
    unittest.main()
