import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from llama_cloud import PollingError
from PIL import Image

from app.main import app
from app.services import parse
from app.services.extract import file_context, upload_context
from app.services.sessions import Page, sessions
from tests.fake_database import mock_database


def png_file() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(output, format="PNG")
    return output.getvalue()


def parse_result(*pages):
    return SimpleNamespace(markdown=SimpleNamespace(pages=list(pages)))


class ParseTests(unittest.TestCase):
    def test_disabled_without_key_uses_local_reader(self):
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": ""}), patch("app.services.parse.parse_file") as parse_file:
            text, image_url, status, pages = upload_context("notes.txt", b"hello")
        self.assertEqual((text, image_url, status), file_context("notes.txt", b"hello"))
        self.assertEqual(pages, [Page("1", "hello")])
        parse_file.assert_not_called()

    def test_empty_file_is_not_sent(self):
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "test-key"}), patch("app.services.parse.parse_file") as parse_file:
            text, _, status, _ = upload_context("empty.pdf", b"")
        parse_file.assert_not_called()
        self.assertEqual(text, "")
        self.assertIn("cannot be analyzed", status)

    def test_any_file_type_is_parsed(self):
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "test-key"}), patch(
            "app.services.parse.parse_file", return_value=[(1, "# Report"), (3, "Totals")]
        ) as parse_file:
            self.assertEqual(upload_context("report.pdf", b"%PDF-1.7"), (
                "# Report\n\nTotals", "", "Parsed with LlamaParse.", [Page("1", "# Report"), Page("3", "Totals")],
            ))
        parse_file.assert_called_once_with("report.pdf", b"%PDF-1.7")

    def test_image_keeps_vision_context(self):
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "test-key"}), patch(
            "app.services.parse.parse_file", return_value=[(1, "Chart text")]
        ):
            text, image_url, status, _ = upload_context("chart.png", png_file())
        self.assertEqual(text, "Chart text")
        self.assertTrue(image_url.startswith("data:image/jpeg;base64,"))
        self.assertIn("Parsed with LlamaParse", status)

    def test_failure_falls_back_to_local_reader(self):
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "test-key"}), patch(
            "app.services.parse.parse_file", side_effect=PollingError("failed")
        ):
            text, _, status, _ = upload_context("notes.txt", b"hello")
        self.assertEqual(text, "hello")
        self.assertEqual(status, "LlamaParse could not read this file. Text ready for chat.")

    def test_empty_result_falls_back_to_local_reader(self):
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "test-key"}), patch(
            "app.services.parse.parse_file", return_value=[]
        ):
            text, _, status, _ = upload_context("tool.exe", b"MZ")
        self.assertEqual(text, "")
        self.assertTrue(status.startswith("LlamaParse found no readable text."))

    def test_parse_file_keeps_successful_pages(self):
        client = MagicMock()
        client.parsing.parse.return_value = parse_result(
            SimpleNamespace(success=True, markdown="Page one", page_number=1),
            SimpleNamespace(success=False, error="bad page", page_number=2),
            SimpleNamespace(success=True, markdown="Page three", page_number=3),
        )
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "test-key", "LLAMA_PARSE_TIER": "agentic"}), patch(
            "app.services.parse.LlamaCloud", return_value=client
        ) as factory:
            self.assertEqual(parse.parse_file("deck.pptx", b"data"), [(1, "Page one"), (3, "Page three")])
        factory.assert_called_once_with(api_key="test-key", timeout=60, max_retries=2)
        client.parsing.parse.assert_called_once_with(
            tier="agentic", version="latest", upload_file=("deck.pptx", b"data"),
            expand=["markdown"], timeout=parse.PARSE_TIMEOUT,
        )

    def test_unknown_tier_uses_default(self):
        with patch.dict(os.environ, {"LLAMA_PARSE_TIER": "premium"}):
            self.assertEqual(parse.tier(), "cost_effective")
        with patch.dict(os.environ, {"LLAMA_PARSE_TIER": ""}):
            self.assertEqual(parse.tier(), "cost_effective")


class ParseUploadTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)
        self.database = mock_database(self)

    def tearDown(self):
        self.client.close()
        sessions.clear()

    def test_upload_reports_llamaparse_status(self):
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "test-key"}), patch(
            "app.services.parse.parse_file", return_value=[(1, "Sheet rows")]
        ):
            response = self.client.post('/api/document', files={'file': ('table.xlsx', b'data')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'Parsed with LlamaParse.')
        download = self.client.get('/api/document/download')
        self.assertEqual(download.content, b'data')


if __name__ == '__main__':
    unittest.main()
