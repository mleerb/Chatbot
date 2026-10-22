import os
import unittest
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
        expected = [
            {"role": "user", "content": "Xin chào", "sources": [], "attachments": []},
            {"role": "assistant", "content": "Chào bạn", "sources": sources, "attachments": []},
        ]
        self.assertEqual(repository.messages(self.user["id"], conversation_id=self.chat["id"]), expected)
        self.assertEqual(repository.messages(self.user["id"], limit=1, conversation_id=self.chat["id"]), expected[-1:])
        self.assertEqual(repository.messages(self.user["id"], limit=0), [])
        self.assertEqual(len(repository.messages(self.user["id"])), 4)
        self.assertEqual(repository.messages(self.user["id"], limit=2), repository.messages(
            self.user["id"], conversation_id=second["id"]))
        self.assertEqual(repository.messages(999999, conversation_id=self.chat["id"]), [])

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
            {"role": "user", "content": "Legacy", "sources": []}])
        self.assertEqual(len(repository.conversations(second_user)), 1)
        self.assertEqual(repository.messages(second_user)[0]["content"], "Old answer")
        with self.engine.connect() as connection:
            columns = {column["name"]: column for column in inspect(connection).get_columns("chat_messages")}
            self.assertFalse(columns["conversation_id"]["nullable"])
            self.assertIsNotNone(connection.scalar(select(Message.conversation_id).where(Message.user_id == second_user)))
        self.assertEqual(repository.delete_conversation(self.user["id"], self.chat["id"]), {"id": self.chat["id"]})
        self.assertEqual(repository.messages(self.user["id"]), [])
