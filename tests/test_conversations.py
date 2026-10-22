import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.sessions import sessions
from tests.fake_database import mock_database


class ConversationTests(unittest.TestCase):
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

    def send(self, question):
        with patch('app.services.chat.make_agent', return_value=object()), patch(
            'app.services.chat.answer_question', return_value='Answer'
        ):
            return self.client.post('/api/chat', json={'message': question})

    def test_create_select_and_history_isolation(self):
        first = self.client.get('/api/state').json()['conversation_id']
        self.assertEqual(self.send('First question').status_code, 200)
        self.client.post('/api/document', files={'file': ('private.txt', b'private')})
        second = self.client.post('/api/conversations')
        self.assertEqual(second.status_code, 201)
        second_id = second.json()['id']
        state = self.client.get('/api/state').json()
        self.assertEqual(state['conversation_id'], second_id)
        self.assertEqual(state['messages'], [])
        self.assertEqual(state['uploads'], [])
        self.assertEqual(self.send('Second question').status_code, 200)
        self.client.post(f'/api/conversations/{first}/select')
        self.assertEqual(self.client.get('/api/state').json()['messages'][0]['content'], 'First question')
        with patch('app.services.chat.make_agent', return_value=object()), patch(
            'app.services.chat.answer_question', side_effect=lambda *args, **kwargs: (
                self.assertEqual(len(args[2]), 2),
                self.assertEqual(args[2][0]['content'], 'First question'),
                'Follow up',
            )[-1]
        ):
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Continue'}).status_code, 200)

    def test_rename_pin_order_and_session_reset(self):
        first = self.client.get('/api/state').json()['conversation_id']
        second = self.client.post('/api/conversations').json()['id']
        renamed = self.client.patch(f'/api/conversations/{first}', json={'title': '  Project notes  ', 'pinned': True})
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()['title'], 'Project notes')
        self.assertTrue(renamed.json()['pinned'])
        self.assertEqual([item['id'] for item in self.client.get('/api/conversations').json()], [first, second])
        sessions.clear()
        self.client.cookies.clear()
        self.client.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
        self.client.post('/api/users/1/select')
        state = self.client.get('/api/state').json()
        self.assertEqual(state['conversation_id'], first)
        self.assertEqual(state['conversations'][0]['title'], 'Project notes')
        self.client.patch(f'/api/conversations/{first}', json={'pinned': False})
        self.assertEqual([item['id'] for item in self.client.get('/api/conversations').json()], [second, first])

    def test_delete_active_and_last_conversation(self):
        first = self.client.get('/api/state').json()['conversation_id']
        self.send('Keep this')
        second = self.client.post('/api/conversations').json()['id']
        self.send('Delete this')
        self.client.post('/api/document', files={'file': ('private.txt', b'private')})
        self.assertEqual(self.client.delete(f'/api/conversations/{second}').json(), {'ok': True})
        state = self.client.get('/api/state').json()
        self.assertEqual(state['conversation_id'], first)
        self.assertEqual(state['messages'][0]['content'], 'Keep this')
        self.assertEqual(state['uploads'], [])
        self.assertEqual(len(self.database.messages(1)), 2)
        self.client.delete(f'/api/conversations/{first}')
        state = self.client.get('/api/state').json()
        self.assertIsNone(state['conversation_id'])
        self.assertEqual(state['conversations'], [])
        self.assertEqual(state['messages'], [])
        self.assertEqual(self.send('Start again').status_code, 200)
        self.assertEqual(len(self.client.get('/api/state').json()['conversations']), 1)

    def test_delete_inactive_keeps_active_files_and_history(self):
        first = self.client.get('/api/state').json()['conversation_id']
        second = self.client.post('/api/conversations').json()['id']
        self.send('Keep this')
        self.client.post('/api/document', files={'file': ('keep.txt', b'keep')})
        self.client.delete(f'/api/conversations/{first}')
        state = self.client.get('/api/state').json()
        self.assertEqual(state['conversation_id'], second)
        self.assertEqual(len(state['uploads']), 1)
        self.assertEqual(len(state['messages']), 2)

    def test_validation_and_user_scoping(self):
        first = self.client.get('/api/state').json()['conversation_id']
        for payload in ({'title': ''}, {'title': '   '}, {'title': 'x' * 101}, {'pinned': 'invalid'}):
            self.assertEqual(self.client.patch(f'/api/conversations/{first}', json=payload).status_code, 422)
        self.client.post('/api/auth/register', json={'name': 'Other', 'email': 'other@example.com', 'password': 'test-password-123'})
        self.assertEqual(self.client.post(f'/api/conversations/{first}/select').status_code, 404)
        self.assertEqual(self.client.patch(f'/api/conversations/{first}', json={'title': 'No'}).status_code, 404)
        self.assertEqual(self.client.delete(f'/api/conversations/{first}').status_code, 404)
        sessions.clear()
        self.client.cookies.clear()
        for method, path, payload in (
            ('GET', '/api/conversations', None), ('POST', '/api/conversations', None),
            ('POST', f'/api/conversations/{first}/select', None),
            ('PATCH', f'/api/conversations/{first}', {'pinned': True}),
            ('DELETE', f'/api/conversations/{first}', None),
        ):
            self.assertEqual(self.client.request(method, path, json=payload).status_code, 401)

    def test_other_session_deletion_clears_stale_context(self):
        first = self.client.get('/api/state').json()['conversation_id']
        self.send('Private context')
        self.client.post('/api/document', files={'file': ('private.txt', b'private')})
        with TestClient(app) as other:
            other.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
            other.delete(f'/api/conversations/{first}')
        state = self.client.get('/api/state').json()
        self.assertIsNone(state['conversation_id'])
        self.assertEqual(state['messages'], [])
        self.assertEqual(state['uploads'], [])
        self.assertEqual(self.send('Fresh context').status_code, 200)


if __name__ == '__main__':
    unittest.main()
