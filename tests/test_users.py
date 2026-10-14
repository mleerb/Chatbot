import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.sessions import sessions
from app.main import app
from tests.fake_database import mock_database


class UserTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)
        self.database = mock_database(self)

    def tearDown(self):
        self.client.close()
        sessions.clear()

    def test_users_history_survives_session_reset_and_switching(self):
        self.assertEqual(self.client.get('/api/users').json(), [{'id': 1, 'name': 'Tester'}])
        self.assertEqual(self.client.post('/api/users', json={'name': '  '}).status_code, 422)
        with patch('app.routers.chat.make_agent', return_value=object()), patch(
            'app.routers.chat.answer_question', return_value='First answer'
        ) as answer:
            self.assertEqual(self.client.post('/api/chat', json={'message': 'First question'}).status_code, 200)
            second = self.client.post('/api/users', json={'name': 'Second'}).json()
            self.assertEqual(second['id'], 2)
            self.client.post('/api/document', files={'file': ('private.md', b'private')})
            self.client.post('/api/users/2/select')
            self.assertEqual(self.client.get('/api/state').json()['filename'], '')
            self.assertEqual(self.client.get('/api/state').json()['messages'], [])
            self.assertEqual(self.client.get('/api/users/1/messages').status_code, 403)
            self.client.post('/api/users/1/select')
            self.assertEqual(self.client.get('/api/users/1/messages').json()[0]['content'], 'First question')
            self.assertEqual(self.client.get('/api/state').json()['filename'], '')
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Follow up'}).status_code, 200)
            self.assertEqual(answer.call_args.args[2][0]['content'], 'First question')
        sessions.clear()
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/chat', json={'message': 'No user'}).status_code, 400)
        self.assertEqual(self.client.post('/api/users/999/select').status_code, 404)
        self.client.post('/api/users/1/select')
        self.assertEqual(len(self.client.get('/api/users/1/messages').json()), 4)

    def test_save_failure_does_not_report_success(self):
        with patch('app.routers.chat.make_agent', return_value=object()), patch(
            'app.routers.chat.answer_question', return_value='Answer'
        ), patch('app.routers.chat.database.save_turn', side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Question'}).status_code, 503)
        self.assertEqual(self.client.get('/api/state').json()['messages'], [])


if __name__ == '__main__':
    unittest.main()
