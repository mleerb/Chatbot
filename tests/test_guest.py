import unittest
from contextlib import ExitStack
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import attempts
from app.services.sessions import COOKIE, sessions
from tests.fake_database import mock_database


class GuestTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        attempts.clear()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(sessions.clear)
        self.database = mock_database(self)
        self.client.post('/api/auth/logout')
        self.no_database = ExitStack()
        for name in ('users', 'get_user', 'messages', 'conversations', 'create_user', 'create_conversation',
                     'get_conversation', 'update_conversation', 'delete_conversation', 'save_turn',
                     'create_account', 'account_by_email'):
            self.no_database.enter_context(patch(f'app.db.repository.{name}', side_effect=AssertionError('Guest database access')))
        self.addCleanup(self.no_database.close)

    def start_guest(self, client=None):
        client = client or self.client
        response = client.post('/api/auth/guest')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['guest'])
        client.headers['x-guest-session'] = response.json()['guest_token']
        return response

    def send(self, text='Question', client=None):
        with patch('app.services.chat.make_agent'), patch('app.services.chat.answer_question', return_value='Answer'):
            return (client or self.client).post('/api/chat', json={'message': text})

    def test_guest_chat_refresh_context_and_no_database_writes(self):
        self.client.get('/api/auth/me')
        before = self.client.cookies[COOKIE]
        response = self.start_guest()
        self.assertNotEqual(before, response.json()['guest_token'])
        self.assertNotIn(before, sessions)
        self.assertNotIn('set-cookie', response.headers)
        self.assertEqual(self.send('First').status_code, 200)
        with patch('app.services.chat.make_agent'), patch('app.services.chat.answer_question', return_value='Second') as answer:
            self.client.post('/api/chat', json={'message': 'Continue'})
            self.assertEqual(answer.call_args.args[2][0]['content'], 'First')
            self.assertFalse(answer.call_args.kwargs['trace'])
        state = self.client.get('/api/state').json()
        self.assertIsNone(state['user_id'])
        self.assertEqual(len(state['messages']), 4)
        self.assertTrue(self.client.get('/api/auth/me').json()['guest'])
        self.assertEqual(self.client.get('/api/state').json(), state)
        self.start_guest()
        self.assertEqual(self.client.get('/api/state').json(), state)

    def test_history_longer_than_model_context_is_retained_only_in_session(self):
        self.start_guest()
        for index in range(8):
            self.send(str(index))
        self.assertEqual(len(self.client.get('/api/state').json()['messages']), 16)
        token = self.client.headers['x-guest-session']
        self.assertEqual(len(sessions[token].history), 12)
        sessions.clear()
        self.assertEqual(self.client.get('/api/auth/me').status_code, 401)
        self.assertEqual(self.client.get('/api/state').status_code, 401)

    def test_guest_files_and_sessions_are_isolated(self):
        self.start_guest()
        item = self.client.post('/api/document', files={'file': ('note.txt', b'private')}).json()
        self.assertEqual(self.client.get('/api/document/download', params={'file_id': item['id']}).content, b'private')
        self.send()
        chat = self.client.get('/api/state').json()['conversation_id']
        with TestClient(app) as other:
            self.start_guest(other)
            self.assertEqual(other.get('/api/state').json()['messages'], [])
            self.assertEqual(other.get('/api/document/download', params={'file_id': item['id']}).status_code, 404)
            self.assertEqual(other.post(f'/api/conversations/{chat}/select').status_code, 404)
            self.send('Other', other)
            self.assertNotEqual(other.get('/api/state').json()['conversation_id'], chat)
        self.assertEqual(len(self.client.get('/api/state').json()['messages']), 2)
        self.assertEqual(self.client.get('/api/users').status_code, 401)
        self.assertEqual(self.client.post('/api/users/1/select').status_code, 401)
        self.assertEqual(self.client.post('/api/conversations/1/select').status_code, 404)

    def test_new_chat_and_delete_clear_guest_messages_and_files(self):
        self.start_guest()
        self.client.post('/api/document', files={'file': ('note.txt', b'private')})
        self.send()
        old = self.client.get('/api/state').json()['conversation_id']
        response = self.client.post('/api/conversations')
        self.assertEqual(response.status_code, 201)
        current = response.json()['id']
        self.assertNotEqual(old, current)
        state = self.client.get('/api/state').json()
        self.assertEqual(state['messages'], [])
        self.assertEqual(state['uploads'], [])
        self.assertEqual(self.client.patch(f'/api/conversations/{current}', json={'title': 'Temporary'}).status_code, 200)
        self.assertEqual(self.client.patch(f'/api/conversations/{current}', json={'pinned': True}).status_code, 403)
        self.assertEqual(self.client.delete(f'/api/conversations/{current}').status_code, 200)
        self.assertEqual(self.client.get('/api/state').json()['conversations'], [])

    def test_no_idle_expiry_and_logout_revokes_guest_history(self):
        self.start_guest()
        self.send()
        token = self.client.headers['x-guest-session']
        sessions[token].touched -= 60 * 60 * 24 * 30
        self.assertTrue(self.client.get('/api/auth/me').json()['guest'])
        self.assertEqual(len(self.client.get('/api/state').json()['messages']), 2)
        previous = sessions[token]
        self.client.post('/api/auth/logout')
        self.assertEqual(previous.guest_messages, [])
        self.assertFalse(previous.guest)
        self.assertNotIn(token, sessions)

    def test_guest_transition_does_not_save_or_import_messages(self):
        self.start_guest()
        self.send('Unsaved')
        token = self.client.headers['x-guest-session']
        previous = sessions[token]
        self.no_database.close()
        response = self.client.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()['guest'])
        self.assertEqual(previous.guest_messages, [])
        self.assertNotIn(token, sessions)
        del self.client.headers['x-guest-session']
        self.assertEqual(self.client.get('/api/state').json()['messages'], [])
        self.assertEqual(self.database.turns[1], [])
        self.assertEqual(self.client.post('/api/auth/guest').status_code, 409)

    def test_close_cleanup_is_cancelled_by_reload_and_has_no_idle_timeout(self):
        self.start_guest()
        self.send()
        token = self.client.headers['x-guest-session']
        with patch('app.services.auth.threading.Timer') as timer_class:
            self.assertEqual(self.client.post('/api/auth/guest/close').status_code, 200)
            timer = timer_class.return_value
            timer.start.assert_called_once()
            self.assertEqual(len(self.client.get('/api/state').json()['messages']), 2)
            timer.cancel.assert_called_once()
            timer_class.call_args.args[1]()
            self.assertIn(token, sessions)
        with patch('app.services.auth.threading.Timer') as timer_class:
            self.client.post('/api/auth/guest/close')
            timer_class.call_args.args[1]()
            self.assertNotIn(token, sessions)

    def test_guest_token_is_not_in_shared_cookies_and_downloads_require_header(self):
        self.start_guest()
        self.send()
        item = self.client.post('/api/document', files={'file': ('tab.txt', b'tab-only')}).json()
        token = self.client.headers.pop('x-guest-session')
        self.assertFalse(self.client.get('/api/auth/me').json()['guest'])
        self.assertEqual(self.client.get('/api/state').status_code, 401)
        download = self.client.get('/api/document/download', params={'file_id': item['id']}, headers={'x-guest-session': token})
        self.assertEqual(download.content, b'tab-only')

    def test_guest_agent_does_not_export_langfuse_traces(self):
        from app.services.agent import answer_question

        with patch('app.services.agent.trace_chat_turn') as trace, patch('app.services.agent.conversation_messages', return_value=[]):
            from unittest.mock import Mock
            agent = Mock()
            agent.invoke.return_value = {'messages': [Mock(content='Answer')]}
            self.assertEqual(answer_question(agent, 'Question', [], 'guest', trace=False), 'Answer')
            trace.assert_not_called()
            self.assertIsNone(agent.invoke.call_args.kwargs['config'])

    def test_failed_model_turn_does_not_add_guest_messages(self):
        self.start_guest()
        with patch('app.services.chat.make_agent', side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Fail'}).status_code, 502)
        self.assertEqual(self.client.get('/api/state').json()['messages'], [])
