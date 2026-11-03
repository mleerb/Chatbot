import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

import psycopg
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.db import repository
from app.db.models import Message
from app.db.schema import initialize_schema


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.engine = self.make_engine()
        self.addCleanup(self.engine.dispose)
        engine_patch = patch("app.db.connection.get_engine", return_value=self.engine)
        repository_patch = patch("app.db.repository.get_engine", return_value=self.engine)
        engine_patch.start()
        repository_patch.start()
        self.addCleanup(engine_patch.stop)
        self.addCleanup(repository_patch.stop)
        repository.initialize()
        self.user = repository.create_user("Tester")
        self.chat = repository.create_conversation(self.user["id"])

    def make_engine(self):
        engine = create_engine("sqlite://")

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

        return engine

    def save(self, question="Question", answer="Answer", sources=None, chat=None):
        repository.save_turn(self.user["id"], question, answer, sources or [], (chat or self.chat)["id"])

    def test_file_embedding_migration_preserves_data_and_backfill_is_scoped(self):
        repository.save_file(self.user["id"], self.chat["id"], "upload", "embedding-old", "old.txt", b"old",
                             document="original")
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE chat_files DROP COLUMN embeddings"))
        initialize_schema(self.engine)
        initialize_schema(self.engine)
        columns = {column["name"]: column for column in inspect(self.engine).get_columns("chat_files")}
        self.assertTrue(columns["embeddings"]["nullable"])
        row = repository.conversation_files(self.user["id"], self.chat["id"])[0]
        self.assertEqual(row["data"], b"old")
        self.assertIsNone(row["embeddings"])
        self.assertEqual(repository.update_file_embeddings(self.user["id"], self.chat["id"], "embedding-old",
                                                           "stale", b"bad"), 0)
        self.assertEqual(repository.update_file_embeddings(self.user["id"], self.chat["id"], "embedding-old",
                                                           "original", b"vectors"), 1)
        self.assertEqual(repository.conversation_files(self.user["id"], self.chat["id"])[0]["embeddings"], b"vectors")
        repository.delete_files(self.user["id"], self.chat["id"], "embedding-old")
        self.assertEqual(repository.update_file_embeddings(self.user["id"], self.chat["id"], "embedding-old",
                                                           "original", b"vectors"), 0)

    def test_accounts_preserve_legacy_profiles_and_allow_shared_display_names(self):
        first = repository.create_account('first@example.com', 'Tester', 'hashed-password')
        second = repository.create_account('second@example.com', 'Tester', 'another-hash')
        self.assertNotEqual(first['id'], self.user['id'])
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(repository.get_user(self.user['id']), self.user)
        self.assertEqual(repository.account_by_email('first@example.com')['password_hash'], 'hashed-password')
        self.assertIsNone(repository.account_by_email('missing@example.com'))
        with self.assertRaises(IntegrityError):
            repository.create_account('first@example.com', 'Another', 'hash')
        self.assertEqual(len(repository.users()), 3)

    def test_users_and_unique_names(self):
        other = repository.create_user("Alice")
        self.assertEqual(repository.users(), [other, self.user])
        self.assertEqual(repository.get_user(other["id"]), other)
        self.assertIsNone(repository.get_user(999999))
        with self.assertRaises(IntegrityError):
            repository.create_user("Alice")
        self.assertEqual(repository.users(), [other, self.user])

    def test_conversation_updates_ordering_and_ownership(self):
        second = repository.create_conversation(self.user["id"], "Second")
        pinned = repository.update_conversation(self.user["id"], self.chat["id"], title="Pinned", pinned=True)
        self.assertEqual(repository.conversations(self.user["id"]), [pinned, second])
        self.assertEqual(repository.get_conversation(self.user["id"], self.chat["id"]), pinned)
        self.assertEqual(repository.update_conversation(self.user["id"], self.chat["id"]), pinned)
        other = repository.create_user("Other")
        self.assertIsNone(repository.get_conversation(other["id"], self.chat["id"]))
        self.assertIsNone(repository.update_conversation(other["id"], self.chat["id"], title="No", pinned=False))
        self.assertIsNone(repository.delete_conversation(other["id"], self.chat["id"]))
        self.assertIsNone(repository.update_conversation(self.user["id"], 999999, title="No"))
        unpinned = repository.update_conversation(self.user["id"], self.chat["id"], title="", pinned=False)
        self.assertEqual(unpinned["title"], "")
        self.assertFalse(unpinned["pinned"])
        self.assertEqual(repository.conversations(self.user["id"]), [second, unpinned])

    def test_messages_json_order_limit_and_scoping(self):
        sources = [{"title": "Nguồn", "url": "https://example.com"}]
        self.save("Xin chào", "Chào bạn", sources)
        second = repository.create_conversation(self.user["id"], "Second")
        self.save("Another", "Response", chat=second)
        extra = {"stopped": False, "rating": None, "trace_id": None}
        expected = [
            {"role": "user", "content": "Xin chào", "sources": [], "attachments": [], **extra},
            {"role": "assistant", "content": "Chào bạn", "sources": sources, "attachments": [], **extra},
        ]
        self.assertEqual(repository.messages(self.user["id"], conversation_id=self.chat["id"]), expected)
        self.assertEqual(repository.messages(self.user["id"], limit=1, conversation_id=self.chat["id"]), expected[-1:])
        self.assertEqual(repository.messages(self.user["id"], limit=0), [])
        self.assertEqual(len(repository.messages(self.user["id"])), 4)
        self.assertEqual(repository.messages(self.user["id"], limit=2), repository.messages(
            self.user["id"], conversation_id=second["id"]))
        self.assertEqual(repository.messages(999999, conversation_id=self.chat["id"]), [])

    def test_document_source_snapshot_roundtrip_and_authorized_access(self):
        from app.core.errors import ServiceError
        from app.schemas.chat import Message as MessageSchema
        from app.services.citations import Evidence, source_text
        from app.services.sessions import ChatSession, Page, Upload

        content = 'English evidence. Bằng chứng tiếng Việt. <script>alert(1)</script>'
        item = Upload('chính-sách.html', content.encode(), content, '', 'Ready', pages=[Page('1', content)])
        reference = Evidence().read(item, 1, item.pages[0])
        repository.save_file(self.user['id'], self.chat['id'], 'upload', item.id, item.filename, item.data,
                             document=content, pages=[('1', content)])
        self.save('Explain / Giải thích', 'Evidence [D1]', [reference])
        session = ChatSession(user_id=self.user['id'], conversation_id=self.chat['id'], uploads={item.id: item})
        stored = repository.messages(self.user['id'], conversation_id=self.chat['id'])[-1]
        self.assertEqual(stored['sources'][0]['text'], content)
        self.assertNotIn('text', MessageSchema.model_validate(stored).model_dump()['sources'][0])
        self.assertEqual(source_text(session, reference['id'])['text'], content)
        other = repository.create_user('Other source owner')
        other_chat = repository.create_conversation(other['id'])
        with self.assertRaises(ServiceError) as denied:
            source_text(ChatSession(user_id=other['id'], conversation_id=other_chat['id']), reference['id'])
        self.assertEqual(denied.exception.status_code, 404)
        repository.delete_files(self.user['id'], self.chat['id'], item.id)
        with self.assertRaises(ServiceError) as removed:
            source_text(session, reference['id'])
        self.assertEqual(removed.exception.status_code, 404)

    def test_message_attachments_are_saved_and_listed(self):
        attachments = [{"id": "u1", "filename": "report.pdf"}]
        repository.save_turn(self.user["id"], "Read this", "Done", [], self.chat["id"], attachments)
        self.save("Follow-up")
        rows = repository.messages(self.user["id"], conversation_id=self.chat["id"])
        self.assertEqual(rows[0]["attachments"], attachments)
        self.assertEqual(rows[2]["attachments"], [])
        self.assertEqual(repository.attached_file_ids(self.user["id"], self.chat["id"]), {"u1"})
        self.assertEqual(repository.attached_file_ids(999999, self.chat["id"]), set())

    def test_initialization_adds_attachments_to_existing_messages(self):
        self.save("Before upgrade")
        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE chat_messages DROP COLUMN attachments"))
        repository.initialize()
        self.assertEqual(repository.messages(self.user["id"])[0]["attachments"], [])
        repository.save_turn(self.user["id"], "After", "Done", [], self.chat["id"], [{"id": "u2", "filename": "a.txt"}])
        self.assertEqual(repository.attached_file_ids(self.user["id"], self.chat["id"]), {"u2"})

    def test_replacing_from_a_question_drops_later_messages_only_in_that_conversation(self):
        self.save("First", "One")
        self.save("Second", "Two")
        other = repository.create_conversation(self.user["id"], "Other")
        self.save("Elsewhere", "Kept", chat=other)
        repository.save_turn(self.user["id"], "Second again", "Partial", [], self.chat["id"], stopped=True,
                             trace_id="trace-1", replace_from=2)
        rows = repository.messages(self.user["id"], conversation_id=self.chat["id"])
        self.assertEqual([row["content"] for row in rows], ["First", "One", "Second again", "Partial"])
        self.assertTrue(rows[3]["stopped"])
        self.assertEqual(rows[3]["trace_id"], "trace-1")
        self.assertEqual(len(repository.messages(self.user["id"], conversation_id=other["id"])), 2)
        with self.assertRaises(LookupError):
            repository.save_turn(self.user["id"], "Bad", "Bad", [], self.chat["id"], replace_from=1)
        self.assertEqual(len(repository.messages(self.user["id"], conversation_id=self.chat["id"])), 4)

    def test_rating_targets_an_answer_in_the_users_conversation(self):
        repository.save_turn(self.user["id"], "Question", "Answer", [], self.chat["id"], trace_id="trace-2")
        self.assertEqual(repository.rate_message(self.user["id"], self.chat["id"], 1, "up"), {"trace_id": "trace-2"})
        self.assertEqual(repository.messages(self.user["id"])[1]["rating"], "up")
        self.assertIsNone(repository.rate_message(self.user["id"], self.chat["id"], 0, "up"))
        self.assertIsNone(repository.rate_message(self.user["id"], self.chat["id"], 5, "up"))
        self.assertIsNone(repository.rate_message(999999, self.chat["id"], 1, "down"))
        repository.rate_message(self.user["id"], self.chat["id"], 1, None)
        self.assertIsNone(repository.messages(self.user["id"])[1]["rating"])

    def test_initialization_adds_answer_state_to_existing_messages(self):
        self.save("Before upgrade")
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE legacy_messages AS SELECT id, user_id, conversation_id, role, content, sources, "
                "attachments, created_at FROM chat_messages"))
            connection.execute(text("DROP TABLE chat_messages"))
            connection.execute(text("ALTER TABLE legacy_messages RENAME TO chat_messages"))
        repository.initialize()
        row = repository.messages(self.user["id"])[1]
        self.assertEqual((row["stopped"], row["rating"], row["trace_id"]), (False, None, None))
        self.assertIsNotNone(repository.rate_message(self.user["id"], self.chat["id"], 1, "down"))

    def test_files_are_stored_per_conversation_and_removed_with_parents(self):
        other = repository.create_conversation(self.user["id"])
        user_id, chat_id = self.user["id"], self.chat["id"]
        repository.save_file(user_id, chat_id, "upload", "u1", "a.pdf", b"pdf", "text", "", "Ready", [("1", "text")])
        repository.save_file(user_id, chat_id, "revision", "r1", "a.pdf", b"edited", parent_id="u1")
        repository.save_file(user_id, chat_id, "generated", "g1", "out.txt", b"out")
        repository.save_file(user_id, other["id"], "upload", "u2", "b.txt", b"b")
        repository.update_file_text(user_id, "u1", "new text", "", "Edited", [("1", "new text")])
        rows = repository.conversation_files(user_id, chat_id)
        self.assertEqual([row["file_id"] for row in rows], ["u1", "r1", "g1"])
        self.assertEqual(rows[0]["data"], b"pdf")
        self.assertEqual((rows[0]["document"], rows[0]["pages"]), ("new text", [["1", "new text"]]))
        self.assertEqual(rows[1]["parent_id"], "u1")
        self.assertEqual(repository.conversation_files(999999, chat_id), [])
        repository.delete_files(user_id, chat_id, "u1")
        self.assertEqual([row["file_id"] for row in repository.conversation_files(user_id, chat_id)], ["g1"])
        repository.save_file(user_id, chat_id, "upload", "u3", "c.txt", b"c")
        repository.delete_files(user_id, chat_id)
        self.assertEqual([row["file_id"] for row in repository.conversation_files(user_id, chat_id)], ["g1"])
        repository.delete_conversation(user_id, chat_id)
        self.assertEqual(repository.conversation_files(user_id, chat_id), [])
        self.assertEqual([row["file_id"] for row in repository.conversation_files(user_id, other["id"])], ["u2"])

    def test_delete_cascades_only_target_conversation(self):
        self.save()
        second = repository.create_conversation(self.user["id"])
        self.save(chat=second)
        self.assertEqual(repository.delete_conversation(self.user["id"], self.chat["id"]), {"id": self.chat["id"]})
        self.assertEqual(repository.messages(self.user["id"], conversation_id=self.chat["id"]), [])
        self.assertEqual(len(repository.messages(self.user["id"])), 2)
        self.assertIsNone(repository.delete_conversation(self.user["id"], self.chat["id"]))

    def test_failed_turn_rolls_back_both_messages(self):
        with self.assertRaises(IntegrityError):
            self.save(answer=None)
        self.assertEqual(repository.messages(self.user["id"]), [])
        self.save()
        self.assertEqual(len(repository.messages(self.user["id"])), 2)

    def test_repeated_initialization_preserves_history(self):
        self.save()
        before = repository.messages(self.user["id"])
        repository.initialize()
        repository.initialize()
        self.assertEqual(repository.messages(self.user["id"]), before)
        self.assertEqual(repository.conversations(self.user["id"]), [self.chat])

    def test_usage_adds_within_a_day_and_restarts_on_the_next(self):
        today = datetime(2026, 10, 22, 17, tzinfo=timezone.utc)
        tomorrow = today + timedelta(days=1)
        self.assertIsNone(repository.usage(self.user["id"]))
        repository.add_usage(self.user["id"], 10, today)
        repository.add_usage(self.user["id"], 5, today)
        self.assertEqual(repository.usage(self.user["id"])["tokens"], 15)
        self.assertEqual(repository.usage(self.user["id"])["window_start"].replace(tzinfo=timezone.utc), today)
        repository.add_usage(self.user["id"], 7, tomorrow)
        item = repository.usage(self.user["id"])
        self.assertEqual(item["tokens"], 7)
        self.assertEqual(item["window_start"].replace(tzinfo=timezone.utc), tomorrow)
        other = repository.create_user("Other")
        self.assertIsNone(repository.usage(other["id"]))

    def test_upload_count_stops_at_limit_and_restarts_on_the_next_day(self):
        today = datetime(2026, 10, 22, 17, tzinfo=timezone.utc)
        tomorrow = today + timedelta(days=1)
        user = self.user["id"]
        self.assertTrue(repository.add_count(user, "uploads", today, 2))
        repository.add_usage(user, 30, today)
        self.assertTrue(repository.add_count(user, "uploads", today, 2))
        self.assertFalse(repository.add_count(user, "uploads", today, 2))
        self.assertEqual(repository.usage(user)["uploads"], 2)
        self.assertEqual(repository.usage(user)["tokens"], 30)
        self.assertTrue(repository.add_count(user, "uploads", tomorrow, 2))
        item = repository.usage(user)
        self.assertEqual((item["uploads"], item["tokens"]), (1, 0))
        repository.add_usage(user, 5, tomorrow + timedelta(days=1))
        self.assertEqual(repository.usage(user)["uploads"], 0)
        self.assertFalse(repository.add_count(repository.create_user("Nobody")["id"], "uploads", today, 0))

    def test_image_count_is_separate_and_can_be_released(self):
        today = datetime(2026, 10, 22, 17, tzinfo=timezone.utc)
        user = self.user["id"]
        self.assertTrue(repository.add_count(user, "images", today, 1))
        self.assertFalse(repository.add_count(user, "images", today, 1))
        self.assertTrue(repository.add_count(user, "uploads", today, 1))
        repository.remove_count(user, "images", today)
        repository.remove_count(user, "images", today)
        item = repository.usage(user)
        self.assertEqual((item["images"], item["uploads"]), (0, 1))
        with self.assertRaises(ValueError):
            repository.add_count(user, "tokens", today, 1)

    def test_initialization_adds_upload_count_to_existing_usage(self):
        with self.engine.begin() as connection:
            connection.execute(text("DROP TABLE chat_usage"))
            connection.execute(text(
                "CREATE TABLE chat_usage (user_id INTEGER PRIMARY KEY REFERENCES chat_users(id) ON DELETE CASCADE, "
                "tokens BIGINT NOT NULL DEFAULT 0, window_start DATETIME NOT NULL)"))
            connection.execute(text("INSERT INTO chat_usage (user_id, tokens, window_start) VALUES (:id, 9, '2026-10-22 17:00:00')"),
                               {"id": self.user["id"]})
        repository.initialize()
        self.assertEqual(repository.usage(self.user["id"])["uploads"], 0)
        self.assertEqual(repository.usage(self.user["id"])["tokens"], 9)
        self.assertEqual(repository.usage(self.user["id"])["images"], 0)

@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL to run PostgreSQL integration tests")
class PostgresRepositoryTests(RepositoryTests):
    def make_engine(self):
        schema = "test_" + uuid4().hex
        config = os.environ["TEST_DATABASE_URL"]
        engine = create_engine("postgresql+psycopg://", creator=lambda: psycopg.connect(
            config, options=f"-csearch_path={schema}", connect_timeout=5), hide_parameters=True)
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))

        def cleanup():
            try:
                with engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            finally:
                engine.dispose()

        self.addCleanup(cleanup)
        return engine

    def test_auth_api_with_postgresql(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.services.auth import attempts
        from app.services.sessions import COOKIE, sessions

        attempts.clear()
        sessions.clear()
        self.addCleanup(attempts.clear)
        self.addCleanup(sessions.clear)
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/state').status_code, 401)
            response = client.post('/api/auth/register', json={
                'name': 'Real account', 'email': 'real@example.com', 'password': 'test-password-123'})
            self.assertEqual(response.status_code, 201)
            user = response.json()['user']
            self.assertNotEqual(user['id'], self.user['id'])
            token = client.cookies[COOKIE]
            chat = client.get('/api/state').json()['conversation_id']
            repository.save_turn(user['id'], 'Private question', 'Private answer', [], chat)
            self.assertEqual(len(client.get('/api/state').json()['messages']), 2)
            with TestClient(app) as other:
                self.assertEqual(other.get('/api/state').status_code, 401)
                other.post('/api/auth/register', json={
                    'name': 'Other', 'email': 'other@example.com', 'password': 'test-password-123'})
                self.assertEqual(other.post(f'/api/users/{user["id"]}/select').status_code, 403)
                self.assertEqual(other.post(f'/api/conversations/{chat}/select').status_code, 404)
                self.assertEqual(other.get('/api/state').json()['messages'], [])
            client.post('/api/auth/logout')
            self.assertNotIn(token, sessions)
            response = client.post('/api/auth/login', json={
                'email': 'real@example.com', 'password': 'test-password-123'})
            self.assertEqual(response.status_code, 200)
            self.assertNotEqual(client.cookies[COOKIE], token)
            self.assertEqual(len(client.get('/api/state').json()['messages']), 2)

    def test_legacy_history_migration_is_idempotent(self):
        with self.engine.begin() as connection:
            Message.__table__.drop(connection)
            connection.execute(text(
                "CREATE TABLE chat_messages ("
                "id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY, "
                "user_id BIGINT NOT NULL REFERENCES chat_users(id) ON DELETE CASCADE, "
                "role TEXT NOT NULL CHECK (role IN ('user', 'assistant')), content TEXT NOT NULL, "
                "sources JSONB NOT NULL DEFAULT '[]'::jsonb, "
                "created_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            ))
            connection.execute(text(
                "INSERT INTO chat_messages (user_id, role, content) VALUES (:user_id, 'user', 'Legacy')"
            ), {"user_id": self.user["id"]})
            second_user = connection.execute(text(
                "INSERT INTO chat_users (name) VALUES ('Legacy user') RETURNING id"
            )).scalar_one()
            connection.execute(text(
                "INSERT INTO chat_messages (user_id, role, content) VALUES (:user_id, 'assistant', 'Old answer')"
            ), {"user_id": second_user})
        initialize_schema(self.engine)
        initialize_schema(self.engine)
        self.assertEqual(repository.messages(self.user["id"], conversation_id=self.chat["id"]), [
            {"role": "user", "content": "Legacy", "sources": [], "attachments": [], "stopped": False, "rating": None,
             "trace_id": None}])
        self.assertEqual(len(repository.conversations(second_user)), 1)
        self.assertEqual(repository.messages(second_user)[0]["content"], "Old answer")
        with self.engine.connect() as connection:
            columns = {column["name"]: column for column in inspect(connection).get_columns("chat_messages")}
            self.assertFalse(columns["conversation_id"]["nullable"])
            self.assertIsNotNone(connection.scalar(select(Message.conversation_id).where(Message.user_id == second_user)))
        self.assertEqual(repository.delete_conversation(self.user["id"], self.chat["id"]), {"id": self.chat["id"]})
        self.assertEqual(repository.messages(self.user["id"]), [])
