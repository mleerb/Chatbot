import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import pages
from app.services.context import conversation_messages
from app.services.sessions import ChatSession, Page, Upload, sessions, sessions_lock
from app.tools import tools_for_turn
from app.tools.edit import create_edit_tool
from app.tools.pages import create_page_tools
from tests.fake_database import mock_database


def paragraphs(count: int, size: int = 900) -> str:
    return "\n\n".join(f"Paragraph {number} " + "x" * size for number in range(1, count + 1))


def large_upload(**changes) -> Upload:
    page_list = [Page(str(number), f"# Section {number}\n" + f"Body {number} " * 600) for number in range(1, 9)]
    page_list[4] = Page("5", "# Budget\nThe annual budget is 42 million dong. " + "Budget " * 300)
    values = {"filename": "report.pdf", "data": b"pdf", "document": "\n\n".join(page.text for page in page_list),
              "image_url": "", "status": "Parsed with LlamaParse.", "pages": page_list}
    values.update(changes)
    return Upload(**values)


def tools(token: str) -> dict:
    return {tool.name: tool for tool in create_page_tools(token)}


class SplitTests(unittest.TestCase):
    def test_text_pages_respect_size_and_paragraphs(self):
        result = pages.text_pages(paragraphs(10))
        self.assertGreater(len(result), 1)
        self.assertTrue(all(len(page.text) <= pages.PAGE_CHARS for page in result))
        self.assertTrue(all(page.text.startswith("Paragraph") for page in result))
        self.assertEqual([page.label for page in result], [str(number) for number in range(1, len(result) + 1)])
        self.assertEqual(pages.text_pages("   "), [])

    def test_source_pages_keep_numbers_and_split_oversized_pages(self):
        result = pages.source_pages([(2, "Short"), (7, paragraphs(12))])
        self.assertEqual(result[0], Page("2", "Short"))
        self.assertTrue(all(page.label.startswith("7 (part ") for page in result[1:]))
        self.assertTrue(result[-1].label.endswith(f"/{len(result) - 1})"))
        self.assertTrue(all(len(page.text) <= pages.MAX_PAGE_CHARS for page in result))


class PromptTests(unittest.TestCase):
    def test_small_file_is_inlined_and_large_file_is_not(self):
        small = Upload("note.txt", b"hi", "Small note", "", "Text ready for chat.", pages=[Page("1", "Small note")])
        large = large_upload()
        self.assertTrue(pages.is_large(large))
        self.assertFalse(pages.is_large(small))
        content = [message["content"] for message in conversation_messages("Question", [], [small, large])]
        self.assertTrue(any("Small note" in text for text in content))
        notice = next(text for text in content if "too large" in text)
        self.assertIn(f"file_id={large.id}", notice)
        self.assertIn("8 pages", notice)
        self.assertFalse(any("Body 3" in text for text in content))


class PageToolTests(unittest.TestCase):
    def setUp(self):
        self.token, self.other = "page-owner", "page-other"
        self.item = large_upload()
        self.foreign = large_upload(filename="private.pdf")
        with sessions_lock:
            sessions[self.token] = ChatSession(uploads={self.item.id: self.item})
            sessions[self.other] = ChatSession(guest=True, uploads={self.foreign.id: self.foreign})

    def tearDown(self):
        with sessions_lock:
            sessions.pop(self.token, None)
            sessions.pop(self.other, None)

    def test_tools_are_registered_for_each_turn(self):
        names = {tool.name for tool in tools_for_turn(self.token, "Question", [])}
        self.assertTrue({"get_outline", "read_page", "search_in_file"} <= names)

    def test_read_page_adds_marked_overlap_and_states_coverage(self):
        result = tools(self.token)["read_page"].invoke({"page": 3, "file_id": self.item.id})
        self.assertIn("page 3 of 8", result)
        self.assertIn("Body 3", result)
        self.assertIn("Overlap from the end of page 2", result)
        self.assertIn("Overlap from the start of page 4", result)
        self.assertIn("You read page 3 of 8 only. Other pages were not read.", result)
        self.assertNotIn("Body 1 ", result)
        first = tools(self.token)["read_page"].invoke({"page": 1})
        self.assertNotIn("end of page 0", first)
        self.assertIn("does not exist", tools(self.token)["read_page"].invoke({"page": 9}))

    def test_outline_lists_previews_without_claiming_reading(self):
        result = tools(self.token)["get_outline"].invoke({})
        self.assertIn("8 pages", result)
        self.assertIn("- Page 5: Budget", result)
        self.assertIn("no page has been read", result)
        with patch("app.services.pages.MAX_OUTLINE", 3):
            self.assertIn("5 more pages are not listed", tools(self.token)["get_outline"].invoke({}))

    def test_search_ranks_pages_and_returns_snippets(self):
        result = tools(self.token)["search_in_file"].invoke({"query": "annual budget"})
        self.assertIn("- Page 5:", result)
        self.assertIn("42 million dong", result)
        self.assertIn("snippets only", result)
        missing = tools(self.token)["search_in_file"].invoke({"query": "volcano"})
        self.assertIn("matches on 0 of 8 pages", missing)
        self.assertIn("does not prove", missing)

    def test_tools_only_read_files_of_their_own_session(self):
        for name, args in (("get_outline", {}), ("read_page", {"page": 1}), ("search_in_file", {"query": "budget"})):
            result = tools(self.token)[name].invoke({**args, "file_id": self.foreign.id})
            self.assertIn("not found", result)
            self.assertNotIn("private.pdf", result)
        self.assertIn("expired", tools("missing-session")["read_page"].invoke({"page": 1}))

    def test_edit_rebuilds_pages_locally(self):
        item = Upload("notes.txt", b"old text", "old text", "", "Text ready for chat.", pages=[Page("1", "old text")])
        with sessions_lock:
            sessions[self.token].uploads = {item.id: item}
        with patch("app.services.parse.parse_file") as parse_file:
            create_edit_tool(self.token).invoke({"old_text": "old", "new_text": "new", "file_id": item.id})
        parse_file.assert_not_called()
        self.assertEqual(item.pages, [Page("1", "new text")])


class ParseOnceTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)
        self.database = mock_database(self)

    def tearDown(self):
        self.client.close()
        sessions.clear()

    def test_same_file_is_parsed_once_per_session(self):
        with patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "test-key"}), patch(
            "app.services.parse.parse_file", return_value=[(1, "Page one"), (2, "Page two")]
        ) as parse_file:
            first = self.client.post('/api/document', files={'file': ('report.pdf', b'same bytes')}).json()
            second = self.client.post('/api/document', files={'file': ('copy.pdf', b'same bytes')}).json()
            self.client.post('/api/document', files={'file': ('other.pdf', b'other bytes')})
        self.assertEqual(parse_file.call_count, 2)
        self.assertNotEqual(first['id'], second['id'])
        session = next(iter(sessions.values()))
        self.assertEqual(session.uploads[second['id']].pages, [Page("1", "Page one"), Page("2", "Page two")])


if __name__ == '__main__':
    unittest.main()
