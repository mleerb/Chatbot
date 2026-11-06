import json
import os
import struct
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from sqlalchemy import create_engine, inspect, text

from app.db import repository
from app.db.schema import initialize_schema
from app.services import documents, embed, pages, storage
from app.services.sessions import ChatSession, Page, Upload, sessions
from app.tools.edit import create_edit_tool
from app.tools.pages import create_page_tools


def vector(index):
    result = np.zeros(embed.DIMENSIONS, dtype="<f4")
    result[index] = 1
    return result


def fake_request(texts, config):
    return np.asarray([vector(0 if any(word in value.lower() for word in ("revenue", "doanh thu")) else 1)
                       for value in texts])


def upload(name="report.txt", first="Revenue grew by 20 percent."):
    page_list = [Page("1", first + " financial " * 1300), Page("2", "Climate policy " * 1300)]
    document = "\n\n".join(page.text for page in page_list)
    return Upload(name, document.encode(), document, "", "Text ready", pages=page_list)


class HybridTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"EMBEDDING_MODEL": "text-embedding-3-small",
                                                  "OPENAI_API_KEY": "fake", "OPENAI_BASE_URL": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.request = patch("app.services.embed.request", side_effect=fake_request).start()
        self.addCleanup(patch.stopall)
        self.item = upload()
        self.session = ChatSession(guest=True, uploads={self.item.id: self.item})
        self.token = "hybrid-tests"
        sessions[self.token] = self.session
        self.addCleanup(sessions.pop, self.token, None)

    def search(self, query, **kwargs):
        tool = next(tool for tool in create_page_tools(self.token) if tool.name == "search_in_file")
        return tool.invoke({"query": query, **kwargs})

    def test_semantic_cross_language_and_query_cache(self):
        result = self.search("doanh thu")
        self.assertIn("Hybrid search", result)
        self.assertIn("Revenue grew", result)
        self.assertIn("matched by meaning", result)
        self.assertIn(self.item.id, result)
        self.assertEqual(self.request.call_count, 2)
        self.search("doanh thu")
        self.assertEqual(self.request.call_count, 2)
        self.assertEqual(len(self.session.embedding_queries), 1)

    def test_cross_file_search_and_foreign_id(self):
        second = upload("second.txt", "Revenue rose in the second business.")
        self.session.uploads[second.id] = second
        result = self.search("doanh thu")
        self.assertIn("report.txt", result)
        self.assertIn("second.txt", result)
        self.assertIn("not found", self.search("revenue", file_id="foreign"))
        outline = create_page_tools(self.token)[0].invoke({})
        self.assertIn("Choose a file_id", outline)

    def test_disabled_and_provider_failure_keep_keyword_search(self):
        with patch.dict(os.environ, {"EMBEDDING_MODEL": ""}):
            result = self.search("revenue")
        self.assertIn("Keyword-only fallback", result)
        self.request.assert_not_called()
        self.request.side_effect = RuntimeError("unavailable")
        result = self.search("revenue")
        self.assertIn("Revenue grew", result)
        self.assertIn("Keyword-only fallback", result)

    def test_query_failure_and_partial_file_fallback(self):
        embed.prepare(self.item)
        self.request.side_effect = RuntimeError("unavailable")
        result = self.search("revenue")
        self.assertIn("query embedding failed", result)
        self.assertIn("Revenue grew", result)
        second = upload("missing.txt")
        self.session.uploads[second.id] = second
        self.request.side_effect = lambda texts, config: fake_request(texts, config) if len(texts) == 1 else (
            (_ for _ in ()).throw(RuntimeError("unavailable")))
        result = self.search("revenue")
        self.assertIn("Some files have no compatible embeddings", result)

    def test_rank_fusion_rewards_agreement(self):
        self.assertEqual(pages.fuse([[0, 1, 2], [2, 1, 3]])[0], 2)
        self.assertEqual(pages.fuse([[4], [4]]), [4])

    def test_format_model_dimensions_provider_and_hash_validation(self):
        embed.prepare(self.item)
        decoded = embed.unpack(self.item.embeddings, embed.settings())
        self.assertEqual(decoded[1].shape, (2, 512))
        self.assertTrue(np.allclose(np.linalg.norm(decoded[1], axis=1), 1))
        self.assertIsNone(embed.unpack(self.item.embeddings, ("other-model", "")))
        self.assertIsNone(embed.unpack(self.item.embeddings, (embed.settings()[0], "https://other.example")))
        for blob in (b"bad", b"", struct.pack("<I", 2) + b"{}"):
            self.assertIsNone(embed.unpack(blob, embed.settings()))
        size = struct.unpack("<I", self.item.embeddings[:4])[0]
        metadata = json.loads(self.item.embeddings[4:4 + size])
        self.assertEqual(metadata["dimensions"], 512)
        self.assertEqual(metadata["hashes"][0], embed.text_hash(self.item.pages[0].text))

    def test_reuses_unchanged_page_after_edit(self):
        embed.prepare(self.item)
        old = embed.unpack(self.item.embeddings, embed.settings())
        self.item.pages = [Page("1", "Revenue doubled this year."), self.item.pages[1]]
        embed.prepare(self.item)
        self.assertEqual(len(self.request.call_args.args[0]), 1)
        new = embed.unpack(self.item.embeddings, embed.settings())
        np.testing.assert_array_equal(old[1][1], new[1][1])

    def test_edit_tool_reembeds_current_revision(self):
        self.item.pages = pages.text_pages(self.item.document)
        embed.prepare(self.item)
        before = set(embed.unpack(self.item.embeddings, embed.settings())[0])
        self.request.reset_mock()
        result = create_edit_tool(self.token).invoke({"old_text": "20 percent", "new_text": "30 percent"})
        self.assertIn("Edited copy ready", result)
        self.assertIn("30 percent", self.item.document)
        hashes = embed.unpack(self.item.embeddings, embed.settings())[0]
        self.assertGreater(len(before.intersection(hashes)), 0)
        self.assertEqual(sum(len(call.args[0]) for call in self.request.call_args_list), 1)

    def test_upload_embeddings_outside_session_lock_and_fail_open(self):
        with patch("app.services.documents.upload_context", return_value=(self.item.document, "", "ready", self.item.pages)), patch(
            "app.services.guest.check_upload"), patch("app.services.guest.take_upload"), patch(
            "app.services.documents.ensure_active"), patch("app.services.guest.create"):
            self.request.side_effect = lambda texts, config: (
                self.assertFalse(self.session.lock.locked()) or fake_request(texts, config))
            result = documents.upload(self.session, "new.txt", b"data")
            self.assertIsNotNone(self.session.uploads[result["id"]].embeddings)
            self.request.side_effect = RuntimeError("offline")
            result = documents.upload(self.session, "fallback.txt", b"data")
            self.assertIsNone(self.session.uploads[result["id"]].embeddings)

    def test_legacy_backfill_persisted_once_and_guest_never_writes_database(self):
        with patch.object(repository, "update_file_embeddings", side_effect=AssertionError("guest database access")):
            self.search("revenue")
        self.session.guest = False
        self.session.user_id, self.session.conversation_id = 4, 7
        self.item.embeddings = None
        with patch.object(repository, "update_file_embeddings", return_value=1) as save:
            self.search("revenue")
            self.search("revenue")
        save.assert_called_once()
        self.assertEqual(save.call_args.args[:3], (4, 7, self.item.id))

    def test_persistence_failure_retries_without_reembedding(self):
        self.session.guest = False
        self.session.user_id, self.session.conversation_id = 4, 7
        with patch.object(repository, "update_file_embeddings", side_effect=[RuntimeError("db"), 1]) as save:
            self.search("revenue")
            self.assertTrue(self.item.embeddings_dirty)
            count = self.request.call_count
            self.search("revenue")
            self.assertEqual(self.request.call_count, count)
            self.assertFalse(self.item.embeddings_dirty)
            self.assertEqual(save.call_count, 2)

    def test_duplicate_work_and_stale_revision_protection(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: embed.prepare(self.item), range(2)))
        self.assertEqual(self.request.call_count, 1)
        self.item.embeddings = None
        def mutate(texts, config):
            self.item.pages = [Page("1", "new revision")]
            return fake_request(texts, config)
        self.request.side_effect = mutate
        self.assertFalse(embed.prepare(self.item))
        self.assertIsNone(self.item.embeddings)

    def test_removed_item_is_not_persisted_and_small_files_remain_inline(self):
        embed.prepare(self.item)
        self.session.uploads.clear()
        self.session.guest = False
        self.session.user_id, self.session.conversation_id = 4, 7
        with patch.object(repository, "update_file_embeddings") as save:
            storage.save_embeddings(self.session, self.item)
        save.assert_not_called()
        small = Upload("small.txt", b"hello", "hello", "", "ready", pages=[Page("1", "hello")])
        self.assertFalse(embed.prepare(small))
        self.session.uploads[small.id] = small
        self.assertIn("Small files are already included", self.search("hello"))

    def test_failed_edit_storage_preserves_original_pages_and_vectors(self):
        embed.prepare(self.item)
        previous = self.item.document, self.item.pages, self.item.embeddings
        with patch.object(storage, "save_revision", side_effect=RuntimeError("offline")):
            result = create_edit_tool(self.token).invoke({"old_text": "20 percent", "new_text": "30 percent"})
        self.assertIn("no edit saved", result)
        self.assertEqual((self.item.document, self.item.pages, self.item.embeddings), previous)
        self.assertEqual(self.item.edits, [])

    def test_system_prompt_explains_hybrid_provenance_and_reading(self):
        from app.prompts import render_prompt

        result = render_prompt("system.j2")
        self.assertIn("meaning and keyword", result)
        self.assertIn("read_page", result)
        self.assertIn("Semantic similarity is not proof", result)

    def test_model_change_rebuilds_and_cache_is_bounded(self):
        embed.prepare(self.item)
        with patch.dict(os.environ, {"EMBEDDING_MODEL": "different"}):
            self.assertTrue(embed.prepare(self.item))
            self.assertEqual(self.request.call_args.args[1][0], "different")
            with patch.object(embed, "QUERY_CACHE_SIZE", 2):
                for query in ("one", "two", "three"):
                    embed.query_vector(self.session, query, embed.settings())
                self.assertEqual(len(self.session.embedding_queries), 2)
        self.session.clear()
        self.assertEqual(len(self.session.embedding_queries), 0)


class EmbeddingClientTests(unittest.TestCase):
    def test_batching_token_limits_response_order_and_normalization(self):
        def respond(**kwargs):
            return SimpleNamespace(data=[SimpleNamespace(index=index, embedding=vector(index % 2) * 3)
                                         for index in reversed(range(len(kwargs["input"])))])
        client = MagicMock()
        client.embeddings.create.side_effect = respond
        with patch.object(embed, "OpenAI") as factory, patch.object(embed, "BATCH_SIZE", 2), patch.object(
            embed, "MAX_TOKENS", 3):
            factory.return_value.__enter__.return_value = client
            result = embed.request(["many words go into several token chunks", "revenue"], ("model", "https://example.test/v1"))
        self.assertEqual(result.shape, (2, 512))
        self.assertGreater(client.embeddings.create.call_count, 1)
        self.assertTrue(np.allclose(np.linalg.norm(result, axis=1), 1))
        for call in client.embeddings.create.call_args_list:
            self.assertLessEqual(len(call.kwargs["input"]), 2)
            self.assertTrue(all(len(tokens) <= 3 for tokens in call.kwargs["input"]))
        self.assertEqual(factory.call_args.kwargs["timeout"], 60)
        self.assertEqual(factory.call_args.kwargs["max_retries"], 1)

    def test_incomplete_provider_response_is_rejected(self):
        client = MagicMock()
        client.embeddings.create.return_value = SimpleNamespace(data=[])
        with patch.object(embed, "OpenAI") as factory:
            factory.return_value.__enter__.return_value = client
            with self.assertRaises(ValueError):
                embed.request(["text"], ("model", ""))

    def test_invalid_vectors_and_insecure_gateway_are_rejected(self):
        for values in ([[0] * 512], [[float("nan")] * 512], [[1, 2]]):
            with self.assertRaises(ValueError):
                embed.normalize(values)
        with self.assertRaises(ValueError):
            embed.request(["text"], ("model", "http://insecure.test"))


class EmbeddingStorageTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        initialize_schema(self.engine)
        self.database = patch("app.db.connection.get_engine", return_value=self.engine)
        self.database.start()
        self.addCleanup(self.database.stop)
        self.addCleanup(self.engine.dispose)
        self.user_id = repository.create_user("embedding-owner")["id"]
        self.conversation = repository.create_conversation(self.user_id)

    def test_nullable_additive_migration_is_idempotent_and_preserves_rows(self):
        repository.save_file(self.user_id, self.conversation["id"], "upload", "old", "old.txt", b"old")
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE chat_files DROP COLUMN embeddings"))
        initialize_schema(self.engine)
        initialize_schema(self.engine)
        columns = {column["name"]: column for column in inspect(self.engine).get_columns("chat_files")}
        self.assertTrue(columns["embeddings"]["nullable"])
        rows = repository.conversation_files(self.user_id, self.conversation["id"])
        self.assertEqual(rows[0]["data"], b"old")
        self.assertIsNone(rows[0]["embeddings"])

    def test_roundtrip_scoped_backfill_and_revision_storage(self):
        item = upload()
        item.embeddings = embed.pack(("model", ""), [embed.text_hash(page.text) for page in item.pages], [vector(0), vector(1)])
        session = ChatSession(user_id=self.user_id, conversation_id=self.conversation["id"])
        storage.save_upload(session, item)
        storage.load(session)
        self.assertEqual(session.uploads[item.id].embeddings, item.embeddings)
        self.assertEqual(repository.update_file_embeddings(self.user_id, self.conversation["id"], item.id, "stale", b"bad"), 0)
        self.assertEqual(repository.update_file_embeddings(self.user_id, -1, item.id, item.document, b"bad"), 0)
        self.assertEqual(repository.update_file_embeddings(self.user_id, self.conversation["id"], item.id, item.document, b"new"), 1)
        self.assertEqual(repository.conversation_files(self.user_id, self.conversation["id"])[0]["embeddings"], b"new")
