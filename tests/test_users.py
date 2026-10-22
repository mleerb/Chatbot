import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.sessions import sessions
from tests.fake_database import mock_database


class UserTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)
        self.database = mock_database(self)
        self.title = patch('app.services.title.generate', return_value='')
        self.title.start()
        self.addCleanup(self.title.stop)

    def tearDown(self):
        self.client.close()
        sessions.clear()

    def test_history_survives_logout_and_cannot_be_selected_by_another_account(self):
        self.assertEqual(self.client.get('/api/users').json(), [{'id': 1, 'name': 'Tester'}])
        self.assertEqual(self.client.post('/api/users', json={'name': 'Other'}).status_code, 403)
        with patch('app.services.chat.make_agent', return_value=object()), patch(
            'app.services.chat.answer_question', return_value='First answer'
        ):
            self.assertEqual(self.client.post('/api/chat', json={'message': 'First question'}).status_code, 200)
        self.client.post('/api/document', files={'file': ('private.md', b'private')})
        self.client.post('/api/auth/logout')
        self.assertEqual(self.client.get('/api/state').status_code, 401)
        self.client.post('/api/auth/register', json={
            'name': 'Second', 'email': 'second@example.com', 'password': 'test-password-123'})
        self.assertEqual(self.client.get('/api/users').json(), [{'id': 2, 'name': 'Second'}])
        self.assertEqual(self.client.post('/api/users/1/select').status_code, 403)
        self.assertEqual(self.client.get('/api/users/1/messages').status_code, 403)
        self.assertEqual(self.client.get('/api/state').json()['messages'], [])
        self.assertEqual(self.client.get('/api/state').json()['uploads'], [])
        self.client.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
        self.assertEqual([item['filename'] for item in self.client.get('/api/state').json()['uploads']], ['private.md'])
        self.assertEqual(self.client.get('/api/users/1/messages').json()[0]['content'], 'First question')

    def test_save_failure_does_not_report_success(self):
        with patch('app.services.chat.make_agent', return_value=object()), patch(
            'app.services.chat.answer_question', return_value='Answer'
        ), patch('app.db.repository.save_turn', side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Question'}).status_code, 503)
        self.assertEqual(self.client.get('/api/state').json()['messages'], [])
