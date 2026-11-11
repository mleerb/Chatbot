import json
import os
import re
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import documents, workspace
from app.services.extract import upload_context
from app.services.pages import source_pages, text_pages
from app.services.sessions import ChatSession, Upload


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / ".workspace"
        environment = patch.dict(os.environ, {
            "WORKSPACE_EXPORT_ENABLED": "true", "WORKSPACE_EXPORT_GUESTS": "false",
            "WORKSPACE_EXPORT_DIR": str(self.root),
            "LLAMA_CLOUD_API_KEY": "", "EMBEDDING_MODEL": "",
        })
        environment.start()
        self.addCleanup(environment.stop)
        capacity = patch("app.services.documents.repository.check_upload_capacity")
        capacity.start()
        self.addCleanup(capacity.stop)
        self.session = ChatSession(user_id=1, conversation_id=2)

    def item(self, text="Private text\nAnother paragraph"):
        return Upload("notes.txt", text.encode(), text, "", "Text ready for chat.", pages=text_pages(text))

    def test_disabled_and_guest_uploads_never_write(self):
        with patch.dict(os.environ, {"WORKSPACE_EXPORT_ENABLED": "false"}):
            workspace.export_upload(self.session, self.item(), {})
        workspace.export_upload(ChatSession(guest=True), self.item(), {})
        workspace.export_upload(ChatSession(), self.item(), {})
        self.assertFalse(self.root.exists())

    def test_guest_export_requires_both_settings_and_survives_session_clear(self):
        session = ChatSession(guest=True, conversation_id=-1)
        item = self.item("Guest debug text")
        with patch.dict(os.environ, {"WORKSPACE_EXPORT_GUESTS": "true", "WORKSPACE_EXPORT_ENABLED": "false"}):
            workspace.export_upload(session, item, {})
        self.assertFalse(self.root.exists())
        with patch.dict(os.environ, {"WORKSPACE_EXPORT_GUESTS": "true"}):
            workspace.export_upload(session, item, {"parser": "local"})
        exported = session.session_id
        session.clear()
        self.assertNotEqual(session.session_id, exported)
        target = self.root / "uploads" / item.id
        manifest = json.loads((target / "manifest.json").read_text())
        self.assertEqual(manifest["session_kind"], "guest")
        self.assertEqual(manifest["session_id"], exported)
        self.assertIn(f"- Session: {exported} (guest)", (target / "split.md").read_text())
        self.assertIsNone(manifest["user_id"])
        self.assertEqual((target / "chunks/001.txt").read_text(), "Guest debug text")
        self.assertEqual(json.loads((target / "steps.json").read_text())[3]["result"], "guest_upload_in_memory")
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((target / "steps.json").stat().st_mode), 0o600)

    def test_guest_upload_exports_when_explicitly_enabled_without_database_access(self):
        session = ChatSession(guest=True)
        with patch.dict(os.environ, {"WORKSPACE_EXPORT_GUESTS": "true"}), patch(
            "app.services.documents.guest.check_upload"
        ), patch("app.services.documents.guest.take_upload"), patch(
            "app.services.documents.embed.prepare"
        ), patch("app.db.repository.save_file", side_effect=AssertionError("Guest database write")):
            result = documents.upload(session, "guest.txt", b"Guest upload content")
        target = self.root / "uploads" / result["id"]
        self.assertEqual((target / "extracted.txt").read_text(), "Guest upload content")
        self.assertEqual(json.loads((target / "manifest.json").read_text())["session_kind"], "guest")

    def test_account_upload_exports_actual_chunks_and_private_permissions(self):
        text = ("First paragraph with English and tiếng Việt.\n\n" * 200).strip()
        item = self.item(text)
        inspection = {"parser": "local", "parse_result": "not_requested", "extracted": text}
        workspace.export_upload(self.session, item, inspection)
        target = self.root / "uploads" / item.id
        manifest = json.loads((target / "manifest.json").read_text())
        self.assertEqual(manifest["filename"], "notes.txt")
        self.assertEqual(manifest["chunk_count"], len(item.pages))
        self.assertEqual(manifest["context_mode"], "inline")
        self.assertEqual((target / "extracted.txt").read_text(), text)
        self.assertEqual([p.read_text() for p in sorted((target / "chunks").glob("*.txt"))],
                         [p.text for p in item.pages])
        self.assertEqual([entry["label"] for entry in manifest["chunks"]], [p.label for p in item.pages])
        steps = json.loads((target / "steps.json").read_text())
        self.assertEqual([s["step"] for s in steps], ["extract", "split", "embed", "persist", "context"])
        self.assertEqual(steps[2]["result"], "not_needed")
        self.assertRegex(manifest["session_id"], r"^s-[0-9a-f]{8}$")
        self.assertEqual(manifest["session_id"], self.session.session_id)
        summary = (target / "split.md").read_text()
        self.assertIn(f"- Session: {self.session.session_id} (account)", summary)
        self.assertIn("1. Extract: Read locally; LlamaParse was not used.", summary)
        self.assertIn("chunks of at most 3,000 characters at a paragraph break", summary)
        self.assertIn(f"3. Result: {len(item.pages)} chunks in chunks/.", summary)
        rows = re.findall(r"^   \| (chunks/\d{3}\.txt) \| (.+?) \| ([\d,]+) \|", summary, re.MULTILINE)
        self.assertEqual(rows, [(entry["file"], entry["label"], f"{entry['characters']:,}")
                                for entry in manifest["chunks"]])
        self.assertIn("5. Chat context: the whole text is sent", summary)
        self.assertNotIn("First paragraph", summary)
        for path in [self.root, *self.root.rglob("*")]:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700 if path.is_dir() else 0o600)

    def test_llamaparse_exports_pre_split_text_and_real_source_labels(self):
        original = [(5, "x" * 6500), (9, "Second source page")]
        inspection = {}
        with patch("app.services.extract.parse.enabled", return_value=True), patch(
            "app.services.extract.parse.parse_file", return_value=original
        ):
            text, image, status, pages = upload_context("report.pdf", b"synthetic", {}, inspection)
        self.assertEqual([p.label for p in pages], ["5 (part 1/2)", "5 (part 2/2)", "9"])
        item = Upload("report.pdf", b"synthetic", text, image, status, pages=pages)
        workspace.export_upload(self.session, item, inspection)
        target = self.root / "uploads" / item.id
        manifest = json.loads((target / "manifest.json").read_text())
        self.assertEqual(manifest["parser"], "llamaparse")
        self.assertEqual(manifest["source_pages"], [{"label": "5", "characters": 6500},
                                                   {"label": "9", "characters": 18}])
        self.assertEqual((target / "extracted.txt").read_text(), "\n\n".join(t for _, t in original))
        self.assertNotEqual((target / "extracted.txt").read_text(), text)
        self.assertEqual([p.read_text() for p in sorted((target / "chunks").glob("*.txt"))],
                         [p.text for p in source_pages(original)])
        summary = (target / "split.md").read_text()
        self.assertIn("1. Extract: Read by LlamaParse. 6,520 characters in extracted.txt.", summary)
        self.assertIn("LlamaParse returned 2 pages. A page longer than 6,000 characters", summary)
        self.assertIn("   - page 5: 6,500 characters → 2 chunks", summary)
        self.assertIn("   - page 9: 18 characters → 1 chunk\n", summary)
        self.assertIn("| chunks/002.txt | 5 (part 2/2) |", summary)

    def test_parse_cache_and_fallback_results_are_recorded(self):
        for cached in [False, True]:
            inspection, cache = {}, {}
            with patch("app.services.extract.parse.enabled", return_value=True), patch(
                "app.services.extract.parse.parse_file", return_value=[(1, "Extracted")]
            ) as parser:
                if cached:
                    upload_context("file.pdf", b"content", cache)
                upload_context("file.pdf", b"content", cache, inspection)
                self.assertEqual(inspection["parse_result"], "cache_hit" if cached else "requested")
                self.assertEqual(parser.call_count, 1)
        inspection = {}
        with patch("app.services.extract.parse.enabled", return_value=True), patch(
            "app.services.extract.parse.parse_file", side_effect=ValueError("private failure")
        ):
            upload_context("file.txt", b"local text", {}, inspection)
        self.assertEqual(inspection["parser"], "local")
        self.assertEqual(inspection["parse_result"], "failed_local_fallback")
        self.assertEqual(inspection["extracted"], "local text")
        self.assertNotIn("private failure", str(inspection))

    def test_large_file_reports_on_demand_and_unavailable_embeddings(self):
        item = self.item("text " * 7000)
        workspace.export_upload(self.session, item, {"parser": "local"})
        target = self.root / "uploads" / item.id
        self.assertEqual(json.loads((target / "manifest.json").read_text())["context_mode"], "on_demand")
        self.assertEqual(json.loads((target / "steps.json").read_text())[2]["result"], "unavailable")

    def test_guest_upload_integration_never_collects_inspection_or_exports(self):
        session = ChatSession(guest=True, conversation_id=-1)
        with patch("app.services.documents.guest.check_upload"), patch(
            "app.services.documents.guest.take_upload"
        ), patch("app.services.documents.ensure_active"), patch(
            "app.services.documents.storage.save_upload"
        ), patch("app.services.documents.upload_context", return_value=("", "", "Ready", [])) as extract, patch(
            "app.services.documents.workspace.export_upload"
        ) as export:
            documents.upload(session, "notes.txt", b"Guest text")
        extract.assert_called_once_with("notes.txt", b"Guest text", session.parsed)
        export.assert_not_called()
        self.assertFalse(self.root.exists())

    def test_empty_upload_and_embedding_success_are_described_without_vectors(self):
        item = self.item("")
        workspace.export_upload(self.session, item, {"parser": "local", "extracted": ""})
        target = self.root / "uploads" / item.id
        self.assertEqual(json.loads((target / "manifest.json").read_text())["chunk_count"], 0)
        self.assertEqual((target / "extracted.txt").read_text(), "")
        self.assertIn("3. Result: no readable text, so there are no chunks.", (target / "split.md").read_text())
        item = self.item("word " * 7000)
        item.embeddings = b"private synthetic vector bytes"
        workspace.export_upload(self.session, item, {"parser": "local"})
        target = self.root / "uploads" / item.id
        steps = json.loads((target / "steps.json").read_text())
        self.assertEqual(steps[2]["result"], "ready")
        self.assertEqual(steps[2]["dimensions"], 512)
        summary = (target / "split.md").read_text()
        self.assertIn("4. Embedding: Embeddings stored for semantic search.", summary)
        self.assertIn("so the agent searches and reads chunks on demand.", summary)
        for path in target.rglob("*"):
            if path.is_file():
                self.assertNotIn("private synthetic vector bytes", path.read_text())

    def test_session_id_is_random_and_never_a_session_token(self):
        first, second = ChatSession(), ChatSession(guest=True)
        self.assertRegex(first.session_id, r"^s-[0-9a-f]{8}$")
        self.assertNotEqual(first.session_id, second.session_id)
        from fastapi import Response

        from app.services import auth
        from app.services.sessions import sessions, sessions_lock

        session = ChatSession(guest=True, conversation_id=-1)
        with sessions_lock:
            sessions["synthetic-token"] = session
        self.addCleanup(lambda: sessions.pop("synthetic-token", None))
        auth.logout(("synthetic-token", session), Response())
        session.guest, session.conversation_id = True, -1
        item = self.item("Token check")
        with patch.dict(os.environ, {"WORKSPACE_EXPORT_GUESTS": "true"}):
            workspace.export_upload(session, item, {"parser": "local"})
        for path in (self.root / "uploads" / item.id).rglob("*"):
            if path.is_file():
                self.assertNotIn("synthetic-token", path.read_text())

    def test_filename_cannot_break_split_summary(self):
        item = Upload("bad\nname|x.txt", b"Text", "Text", "", "Text ready for chat.", pages=text_pages("Text"))
        workspace.export_upload(self.session, item, {"parser": "local"})
        summary = (self.root / "uploads" / item.id / "split.md").read_text()
        self.assertTrue(summary.startswith("# How bad name x.txt was split\n"))
        self.assertIn("3. Result: 1 chunk in chunks/.", summary)

    def test_unsafe_directory_and_invalid_identifier_are_rejected(self):
        self.root.mkdir(mode=0o755)
        self.root.chmod(0o755)
        with self.assertLogs("app.services.workspace", level="WARNING"):
            workspace.export_upload(self.session, self.item(), {})
        self.assertFalse((self.root / "uploads").exists())
        self.root.chmod(0o700)
        item = self.item()
        item.id = "../../escape"
        with self.assertLogs("app.services.workspace", level="WARNING"):
            workspace.export_upload(self.session, item, {})
        self.assertFalse((self.root / "uploads").exists())
        self.root.rmdir()
        self.root.symlink_to(Path(self.temporary.name), target_is_directory=True)
        with self.assertLogs("app.services.workspace", level="WARNING"):
            workspace.export_upload(self.session, self.item(), {})
        self.assertFalse((Path(self.temporary.name) / "uploads").exists())

    def test_export_failure_does_not_fail_upload_or_log_content(self):
        with patch("app.services.workspace.private_write", side_effect=OSError("private content")):
            with self.assertLogs("app.services.workspace", level="WARNING") as logs:
                workspace.export_upload(self.session, self.item(), {})
        self.assertNotIn("private content", "".join(logs.output))

    def test_upload_integration_only_exports_after_successful_account_save(self):
        with patch("app.services.documents.quota.check_upload"), patch(
            "app.services.documents.quota.take_upload"
        ), patch("app.services.documents.ensure_active"), patch(
            "app.services.documents.storage.save_upload"
        ) as save:
            result = documents.upload(self.session, "notes.txt", b"Actual upload text")
            save.assert_called_once()
        target = self.root / "uploads" / result["id"]
        self.assertEqual((target / "chunks/001.txt").read_text(), "Actual upload text")
        with patch("app.services.documents.quota.check_upload"), patch(
            "app.services.documents.quota.take_upload"
        ), patch("app.services.documents.ensure_active"), patch(
            "app.services.documents.storage.save_upload", side_effect=RuntimeError("offline")
        ), patch("app.services.documents.workspace.export_upload") as export:
            with self.assertRaisesRegex(Exception, "Could not save the file"):
                documents.upload(self.session, "notes.txt", b"Never exported")
            export.assert_not_called()


if __name__ == "__main__":
    unittest.main()
