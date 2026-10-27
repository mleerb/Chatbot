import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import quota
from app.services.sessions import sessions
from tests.fake_database import mock_database


class QuotaTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(sessions.clear)
        self.database = mock_database(self)
        self.title = patch('app.services.title.generate', return_value='')
        self.title.start()
        self.addCleanup(self.title.stop)
        self.limit = patch('app.services.quota.USER_TOKEN_LIMIT', 100)
        self.limit.start()
        self.addCleanup(self.limit.stop)

    def use_tokens(self, tokens):
        def answer(*args, usage, **kwargs):
            usage.append(tokens)
            return 'Answer'

        with patch('app.services.chat.make_agent'), patch('app.services.chat.answer_question', side_effect=answer):
            return self.client.post('/api/chat', json={'message': 'Question'})

    def test_limit_blocks_chat_and_uploads_until_midnight(self):
        self.assertIsNone(self.client.get('/api/state').json()['limit_resets_at'])
        first = self.use_tokens(60)
        self.assertEqual(first.status_code, 200)
        self.assertIsNone(first.json()['limit_resets_at'])
        self.assertFalse(first.json()['guest_limited'])
        reached = self.use_tokens(60)
        self.assertEqual(reached.status_code, 200)
        self.assertEqual(datetime.fromisoformat(reached.json()['limit_resets_at']), quota.next_midnight())
        blocked = self.use_tokens(1)
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()['detail'], quota.LIMIT_MESSAGE)
        self.assertEqual(self.client.post('/api/document', files={'file': ('note.txt', b'x')}).status_code, 403)
        self.assertEqual(self.client.post('/api/conversations').status_code, 201)
        self.assertEqual(self.use_tokens(1).status_code, 403)
        self.assertEqual(self.database.usages[1]['tokens'], 120)
        self.assertEqual(len(self.client.get('/api/conversations').json()), 2)
        midnight = quota.next_midnight()
        with patch('app.services.quota.now', return_value=midnight - timedelta(seconds=1)):
            self.assertIsNotNone(self.client.get('/api/state').json()['limit_resets_at'])
        with patch('app.services.quota.now', return_value=midnight):
            self.assertIsNone(self.client.get('/api/state').json()['limit_resets_at'])
            self.assertEqual(self.use_tokens(10).status_code, 200)
        self.assertEqual(self.database.usages[1]['tokens'], 10)
        self.assertEqual(self.database.usages[1]['window_start'], midnight)

    def test_day_follows_limit_timezone(self):
        evening = datetime(2026, 10, 23, 16, 59, tzinfo=timezone.utc)
        with patch('app.services.quota.now', return_value=evening):
            self.assertEqual(quota.today(), date(2026, 10, 23))
            self.assertEqual(quota.next_midnight(), datetime(2026, 10, 23, 17, tzinfo=timezone.utc))
            self.use_tokens(90)
        with patch('app.services.quota.now', return_value=evening + timedelta(minutes=1)):
            self.assertEqual(quota.today(), date(2026, 10, 24))
            self.assertIsNone(self.use_tokens(20).json()['limit_resets_at'])
        self.assertEqual(self.database.usages[1]['tokens'], 20)

    def test_limit_is_per_account(self):
        self.use_tokens(100)
        self.client.post('/api/auth/logout')
        self.client.post('/api/auth/register', json={
            'name': 'Other', 'email': 'other@example.com', 'password': 'test-password-123'})
        self.assertIsNone(self.client.get('/api/state').json()['limit_resets_at'])
        self.assertEqual(self.use_tokens(10).status_code, 200)
        self.client.post('/api/auth/logout')
        self.client.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
        self.assertIsNotNone(self.client.get('/api/state').json()['limit_resets_at'])

    def test_usage_falls_back_to_estimate_and_failures_keep_the_answer(self):
        with patch('app.services.chat.make_agent'), patch('app.services.chat.answer_question', return_value='Answer'):
            self.client.post('/api/chat', json={'message': '12345678'})
            self.assertEqual(self.database.usages[1]['tokens'], 4)
            with patch('app.db.repository.add_usage', side_effect=RuntimeError('down')):
                self.assertEqual(self.client.post('/api/chat', json={'message': 'Again'}).status_code, 200)
        self.assertEqual(len(self.client.get('/api/state').json()['messages']), 4)

    def upload(self, name='note.txt'):
        return self.client.post('/api/document', files={'file': (name, b'text')})

    def test_upload_limit_counts_files_per_day_and_resets_at_midnight(self):
        with patch('app.services.quota.UPLOAD_LIMIT', 2):
            self.assertIsNone(self.client.get('/api/state').json()['upload_resets_at'])
            first = self.upload()
            self.assertEqual(first.status_code, 200)
            self.assertEqual(self.client.delete('/api/document', params={'file_id': first.json()['id']}).status_code, 200)
            self.assertEqual(self.upload().status_code, 200)
            state = self.client.get('/api/state').json()
            self.assertEqual(datetime.fromisoformat(state['upload_resets_at']), quota.next_midnight())
            self.assertIsNone(state['limit_resets_at'])
            blocked = self.upload()
            self.assertEqual(blocked.status_code, 403)
            self.assertEqual(blocked.json()['detail'], quota.UPLOAD_LIMIT_MESSAGE)
            self.client.post('/api/conversations')
            self.assertEqual(self.upload().status_code, 403)
            self.assertEqual(self.use_tokens(10).status_code, 200)
            self.assertEqual(self.database.usages[1]['uploads'], 2)
            with patch('app.services.quota.now', return_value=quota.next_midnight()):
                self.assertIsNone(self.client.get('/api/state').json()['upload_resets_at'])
                self.assertEqual(self.upload().status_code, 200)
            self.assertEqual(self.database.usages[1]['uploads'], 1)

    def test_token_limit_also_blocks_uploads_before_counting(self):
        self.use_tokens(100)
        self.assertEqual(self.upload().json()['detail'], quota.LIMIT_MESSAGE)
        self.assertEqual(self.database.usages[1]['uploads'], 0)

    def test_new_day_tokens_reset_upload_count(self):
        with patch('app.services.quota.UPLOAD_LIMIT', 1):
            self.upload()
            with patch('app.services.quota.now', return_value=quota.next_midnight()):
                self.use_tokens(10)
                self.assertEqual(self.database.usages[1]['uploads'], 0)
                self.assertEqual(self.upload().status_code, 200)
