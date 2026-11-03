import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.main import app
from app.prompts import render_prompt
from app.services import citations, guest, storage
from app.services.context import conversation_messages
from app.services.sessions import Page, Upload, sessions
from app.tools.edit import create_edit_tool
from app.tools.pages import create_page_tools
from app.tools.search import create_search_tool
from tests.fake_database import mock_database
from tests.test_stream import events, fake_agent, final_turn, text


class CitationTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        guest.meters.clear()
        self.addCleanup(sessions.clear)
        self.addCleanup(guest.meters.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.database = mock_database(self)
        environment = patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "",
                                              "LLAMA_CLOUD_API_KEY": "", "EMBEDDING_MODEL": ""})
        environment.start()
        self.addCleanup(environment.stop)
        title = patch("app.services.title.generate", return_value="")
        title.start()
        self.addCleanup(title.stop)

    def upload(self, content, filename="notes.txt"):
        response = self.client.post("/api/document", files={"file": (filename, content.encode())})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def answer(self, content, run=None):
        agent = fake_agent([])

        def invoke(payload, **kwargs):
            if run:
                run(payload)
            return {"messages": [AIMessage(content=content)]}

        agent.invoke.side_effect = invoke
        with patch("app.services.chat.make_agent", return_value=agent):
            response = self.client.post("/api/chat", json={"message": "Explain / Giải thích"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def source(self, reference, client=None):
        return (client or self.client).get("/api/sources/" + reference["id"])

    def test_small_english_vietnamese_sections_are_citable_and_script_is_literal(self):
        content = 'Returns within thirty days.\nHoàn tiền trong ba mươi ngày.\n<script>window.pwned=1</script>\n<img src=x onerror=alert(1)> {{ literal }}'
        self.upload(content, "chính-sách.html")

        def inspect(payload):
            rendered = str(payload["messages"])
            self.assertIn("Citation: [D1]", rendered)
            self.assertIn("Section 1", rendered)
            self.assertIn("{{ literal }}", rendered)
            self.assertIn("<script>", rendered)

        result = self.answer("Returns / Hoàn tiền. [D1] [D999] [W999]", inspect)
        self.assertEqual(result["display_answer"], "Returns / Hoàn tiền. [D1]  ")
        source = result["sources"][0]
        self.assertEqual((source["kind"], source["location"], source["version"]),
                         ("document", "Section 1", "Original"))
        self.assertNotIn("text", source)
        response = self.source(source)
        self.assertEqual(response.json()["text"], content)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        state = self.client.get("/api/state").json()
        self.assertNotIn("text", state["messages"][-1]["sources"][0])
        self.assertEqual(state["messages"][-1]["sources"], result["sources"])
        messages = conversation_messages("Again", state["messages"])
        self.assertNotIn("[D1]", messages[-2]["content"])

    def test_all_small_sections_labelled_without_inventing_physical_pages(self):
        self.upload("English section. " * 210 + "\n\nTiếng Việt ở phần hai. " * 200)
        result = self.answer("First [D1], second [D2].")
        self.assertEqual([source["location"] for source in result["sources"]], ["Section 1", "Section 2"])
        self.assertIn("Tiếng Việt", self.source(result["sources"][1]).json()["text"])

    def test_outline_and_search_do_not_register_unread_pages(self):
        self.upload("Large English / Tiếng Việt. " * 1200)
        token, session = next(iter(sessions.items()))
        item = session.latest_upload

        def read(payload):
            tools = create_page_tools(token)
            tools[0].invoke({"file_id": item.id})
            tools[2].invoke({"file_id": item.id, "query": "Tiếng Việt"})
            self.assertEqual(session.evidence.documents, [])
            result = tools[1].invoke({"file_id": item.id, "page": 2})
            self.assertIn("[D1]", result)
            tools[1].invoke({"file_id": item.id, "page": 999})
            self.assertEqual(len(session.evidence.documents), 1)

        result = self.answer("Evidence [D1] [D2]", read)
        self.assertEqual(result["display_answer"], "Evidence [D1] ")
        self.assertEqual(self.source(result["sources"][0]).json()["text"], item.pages[1].text)

    def test_parser_pages_and_local_sections_are_distinguished(self):
        item = Upload("report.pdf", b"", "Hello / Xin chào", "", "Parsed with LlamaParse.",
                      pages=[Page("5 (part 2/3)", "Hello / Xin chào")])
        evidence = citations.Evidence()
        self.assertEqual(evidence.read(item, 1, item.pages[0])["location"], "Page 5 (part 2/3)")
        self.assertIn("[D1]", render_prompt("section.j2", source=evidence.documents[0]))

    def test_old_and_new_revisions_in_same_turn_and_after_reload(self):
        self.upload("Old English. Tiếng Việt cũ.")
        token, session = next(iter(sessions.items()))
        item = session.latest_upload

        def edit(payload):
            result = create_edit_tool(token).invoke({"file_id": item.id, "old_text": "Old English. Tiếng Việt cũ.",
                                                    "new_text": "New English. Tiếng Việt mới."})
            self.assertIn("ready for download", result)
            read = create_page_tools(token)[1].invoke({"file_id": item.id, "page": 1})
            self.assertIn("[D2]", read)

        result = self.answer("Before [D1]. After [D2].", edit)
        old, new = result["sources"]
        self.assertNotEqual(old["revision"], new["revision"])
        self.assertEqual(old["revision_id"], item.id)
        self.assertEqual(new["revision_id"], item.edits[-1].id)
        self.assertEqual(self.source(old).json()["text"], "Old English. Tiếng Việt cũ.")
        self.assertEqual(self.source(new).json()["text"], "New English. Tiếng Việt mới.")
        session.uploads.clear()
        storage.load(session)
        self.assertEqual(self.source(old).json()["text"], "Old English. Tiếng Việt cũ.")
        self.assertEqual(self.source(new).json()["text"], "New English. Tiếng Việt mới.")
        self.client.post("/api/auth/logout")
        self.client.post("/api/auth/login", json={"email": "tester@example.com", "password": "test-password-123"})
        self.assertEqual(self.source(old).json()["text"], "Old English. Tiếng Việt cũ.")
        self.assertEqual(self.source(new).json()["text"], "New English. Tiếng Việt mới.")

    def test_web_markers_are_distinct_and_stable_across_searches(self):
        self.upload("Document evidence / Bằng chứng tài liệu.")

        def search(payload):
            session = next(iter(sessions.values()))
            tool = create_search_tool("public question", session.evidence.web)
            with patch("app.tools.search.search_web", return_value=[
                {"title": "Web / Nguồn", "url": "https://example.com", "content": "Public evidence"}
            ]):
                self.assertIn("[W1]", tool.invoke({}))
                self.assertIn("[W1]", tool.invoke({}))

        result = self.answer("Document [D1]. Web [W1].", search)
        self.assertEqual([source["marker"] for source in result["sources"]], ["D1", "W1"])
        self.assertEqual([source["kind"] for source in result["sources"]], ["document", "web"])

    def test_removed_source_and_other_conversation_return_404(self):
        upload = self.upload("Private English / Tiếng Việt riêng tư.")
        result = self.answer("Private [D1]")
        source = result["sources"][0]
        conversation = self.client.get("/api/state").json()["conversation_id"]
        self.client.post("/api/conversations")
        self.assertEqual(self.source(source).status_code, 404)
        self.client.post(f"/api/conversations/{conversation}/select")
        self.assertEqual(self.source(source).status_code, 200)
        self.client.delete("/api/document", params={"file_id": upload["id"]})
        self.assertEqual(self.source(source).status_code, 404)

    def test_account_and_guests_cannot_guess_another_owners_source(self):
        self.upload("Private account / Tài khoản riêng tư.")
        account_source = self.answer("Account [D1]")["sources"][0]
        other = TestClient(app)
        self.addCleanup(other.close)
        self.assertEqual(self.source(account_source, other).status_code, 401)
        registered = other.post("/api/auth/register", json={"name": "Other", "email": "other@example.com",
                                                           "password": "other-password-123"})
        self.assertEqual(registered.status_code, 201)
        self.assertEqual(self.source(account_source, other).status_code, 404)
        other.post("/api/auth/logout")
        guest_token = other.post("/api/auth/guest").json()["guest_token"]
        other.headers["x-guest-session"] = guest_token
        self.assertEqual(self.source(account_source, other).status_code, 404)
        self.client.post("/api/auth/logout")
        token = self.client.post("/api/auth/guest").json()["guest_token"]
        self.client.headers["x-guest-session"] = token
        self.upload("Private guest / Khách riêng tư.")
        with patch("app.db.repository.messages") as stored_messages, patch("app.db.repository.conversation_files") as stored_files:
            guest_source = self.answer("Guest [D1]")["sources"][0]
            self.assertEqual(self.source(guest_source).status_code, 200)
            self.assertEqual(self.source(guest_source, other).status_code, 404)
            stored_messages.assert_not_called()
            stored_files.assert_not_called()
        other.headers.pop("x-guest-session")
        other.post("/api/auth/login", json={"email": "other@example.com", "password": "other-password-123"})
        self.assertEqual(self.source(guest_source, other).status_code, 404)

    def test_stream_splits_markers_and_filters_invented_or_truncated_markers(self):
        self.upload("English evidence. Bằng chứng tiếng Việt.")
        script = [text("English / Tiếng Việt ["), text("D"), text("1"), text("] [D999] [W999] [D"),
                  final_turn("English / Tiếng Việt [D1] [D999] [W999] [D")]
        with patch("app.services.chat.make_agent", return_value=fake_agent(script)):
            result = events(self.client.post("/api/chat/stream", json={"message": "Explain"}))
        visible = "".join(event["text"] for event in result if event["type"] == "text")
        self.assertEqual(visible, "English / Tiếng Việt [D1]   ")
        for event in result:
            if event["type"] == "text":
                self.assertNotIn("D999", event["text"])
        self.assertEqual(result[-1]["display_answer"], visible)
        self.assertEqual(result[-1]["sources"][0]["marker"], "D1")

    def test_stop_in_middle_of_marker_keeps_only_complete_valid_citations(self):
        self.upload("English and Vietnamese / Tiếng Anh và tiếng Việt.")
        script = [text("Evidence [D1] "), text("[D"), text("2"), text("]"), final_turn("Never completed")]

        def before(index):
            if index == 2:
                self.assertTrue(self.client.post("/api/chat/stop").json()["stopped"])

        with patch("app.services.chat.make_agent", return_value=fake_agent(script, before)):
            result = events(self.client.post("/api/chat/stream", json={"message": "Stop test"}))
        self.assertTrue(result[-1]["stopped"])
        self.assertEqual(result[-1]["display_answer"], "Evidence [D1] ")
        self.assertEqual([source["marker"] for source in result[-1]["sources"]], ["D1"])
        self.assertEqual(self.client.get("/api/state").json()["messages"][-1]["content"], "Evidence [D1] ")

    def test_replacing_answer_revokes_old_source_and_creates_new_snapshot(self):
        self.upload("English source. Nguồn tiếng Việt.")
        old = self.answer("Original answer [D1]")["sources"][0]
        agent = fake_agent([])
        agent.invoke.return_value = {"messages": [AIMessage(content="Replacement [D1]")]}
        with patch("app.services.chat.make_agent", return_value=agent):
            result = self.client.post("/api/chat", json={"message": "Again / Lại", "replace_from": 0})
        self.assertEqual(result.status_code, 200)
        new = result.json()["sources"][0]
        self.assertNotEqual(old["id"], new["id"])
        self.assertEqual(self.source(old).status_code, 404)
        self.assertEqual(self.source(new).json()["text"], "English source. Nguồn tiếng Việt.")

    def test_stopped_partial_marker_without_completed_citation_has_no_document_sources(self):
        self.upload("English / Tiếng Việt")
        script = [text("Partial / Dở [D"), text("1"), final_turn("Unfinished")]

        def before(index):
            if index == 1:
                self.client.post("/api/chat/stop")

        with patch("app.services.chat.make_agent", return_value=fake_agent(script, before)):
            result = events(self.client.post("/api/chat/stream", json={"message": "Stop"}))
        self.assertTrue(result[-1]["stopped"])
        self.assertEqual(result[-1]["display_answer"], "Partial / Dở ")
        self.assertEqual(result[-1]["sources"], [])

    def test_failed_turn_does_not_leave_openable_sources(self):
        self.upload("English / Tiếng Việt")
        captured = []

        def fail(payload, **kwargs):
            captured.extend(next(iter(sessions.values())).evidence.documents)
            raise RuntimeError("provider offline")

        agent = fake_agent([])
        agent.invoke.side_effect = fail
        with patch("app.services.chat.make_agent", return_value=agent):
            self.assertEqual(self.client.post("/api/chat", json={"message": "Fail"}).status_code, 502)
        self.assertTrue(captured)
        self.assertEqual(self.source(captured[0]).status_code, 404)
        self.assertIsNone(next(iter(sessions.values())).evidence)


class CitationFilterTests(unittest.TestCase):
    def test_incremental_filter_never_exposes_partial_markers(self):
        evidence = citations.Evidence()
        item = Upload("notes.txt", b"", "Hello / Xin chào", "", "Ready", pages=[Page("1", "Hello / Xin chào")])
        evidence.read(item, 1, item.pages[0])
        stream = citations.CitationStream(evidence)
        visible = ""
        for chunk in ("Hello ", "[", "D", "1", "]", " [D999]", " [W1]", " [D"):
            visible += stream.feed(chunk)
            self.assertFalse(visible.endswith(("[", "[D", "[D1")))
        self.assertEqual(visible, "Hello [D1]   ")
        self.assertEqual(citations.clean("[Download](https://example.com)", evidence), "[Download](https://example.com)")
