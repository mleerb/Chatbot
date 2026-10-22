import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.sessions import Page, sessions
from app.tools.create import create_file_tool
from app.tools.edit import create_edit_tool
from tests.fake_database import mock_database

LOGIN = {'email': 'tester@example.com', 'password': 'test-password-123'}


class StorageTests(unittest.TestCase):
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

    def state(self, client=None):
        return (client or self.client).get('/api/state').json()

    def run_tool(self, factory, arguments):
        def answer(agent, *args, **kwargs):
            agent.invoke(arguments)
            return 'Done'
        with patch('app.services.chat.make_agent', side_effect=lambda token, question, sources: factory(token)), patch(
            'app.services.chat.answer_question', side_effect=answer
        ):
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Do it'}).status_code, 200)

    def test_files_follow_their_conversation_and_survive_logout(self):
        first = self.state()['conversation_id']
        item = self.client.post('/api/document', files={'file': ('notes.txt', b'hello')}).json()
        second = self.client.post('/api/conversations').json()['id']
        self.assertEqual(self.state()['uploads'], [])
        self.client.post(f'/api/conversations/{first}/select')
        self.assertEqual([upload['id'] for upload in self.state()['uploads']], [item['id']])
        self.client.post('/api/auth/logout')
        self.client.post('/api/auth/login', json=LOGIN)
        self.client.post(f'/api/conversations/{first}/select')
        self.assertEqual(self.client.get('/api/document/download', params={'file_id': item['id']}).content, b'hello')
        session = next(iter(sessions.values()))
        self.assertEqual(session.uploads[item['id']].pages, [Page('1', 'hello')])
        self.client.post(f'/api/conversations/{second}/select')
        self.assertEqual(self.state()['uploads'], [])

    def test_revisions_and_generated_files_are_restored(self):
        item = self.client.post('/api/document', files={'file': ('notes.txt', b'old text')}).json()
        self.run_tool(create_edit_tool, {'old_text': 'old', 'new_text': 'new', 'file_id': item['id']})
        self.run_tool(create_file_tool, {'filename': 'summary.md', 'content': '# Summary'})
        with TestClient(app) as other:
            other.post('/api/auth/login', json=LOGIN)
            state = self.state(other)
            self.assertEqual(len(state['uploads'][0]['edits']), 1)
            self.assertEqual(other.get('/api/document/edited').content, b'new text')
            self.assertEqual([file['filename'] for file in state['generated_files']], ['summary.md'])
            restored = next(session for session in sessions.values() if session.uploads)
        self.assertEqual(restored.uploads[item['id']].document, 'new text')

    def test_removing_files_and_conversations_deletes_stored_copies(self):
        first = self.client.post('/api/document', files={'file': ('a.txt', b'a')}).json()
        self.client.post('/api/document', files={'file': ('b.txt', b'b')})
        self.client.delete('/api/document', params={'file_id': first['id']})
        self.assertEqual([item['filename'] for item in self.database.files.values()], ['b.txt'])
        conversation = self.state()['conversation_id']
        self.client.delete(f'/api/conversations/{conversation}')
        self.assertEqual(self.database.files, {})

    def test_other_accounts_cannot_load_files(self):
        self.client.post('/api/document', files={'file': ('private.txt', b'private')})
        with TestClient(app) as other:
            other.post('/api/auth/register', json={'name': 'Other', 'email': 'other@example.com',
                                                   'password': 'test-password-123'})
            self.assertEqual(self.state(other)['uploads'], [])
            for conversation in [key for key, chat in self.database.chats.items() if chat['user_id'] == 1]:
                self.assertEqual(other.post(f'/api/conversations/{conversation}/select').status_code, 404)

    def send(self, client, message, **options):
        with patch('app.services.chat.make_agent', return_value=object()), patch(
            'app.services.chat.answer_question', **(options or {'return_value': 'Answer'})
        ):
            return client.post('/api/chat', json={'message': message})

    def test_files_are_sent_with_the_next_message(self):
        item = self.client.post('/api/document', files={'file': ('report.txt', b'report')}).json()
        self.assertFalse(item['sent'])
        self.assertEqual(self.send(self.client, 'Fails', side_effect=RuntimeError('down')).status_code, 502)
        self.assertFalse(self.state()['uploads'][0]['sent'])
        self.assertEqual(self.send(self.client, 'Read it').status_code, 200)
        state = self.state()
        self.assertTrue(state['uploads'][0]['sent'])
        self.assertEqual(state['messages'][0]['attachments'], [{'id': item['id'], 'filename': 'report.txt'}])
        self.send(self.client, 'Follow-up')
        self.assertEqual(self.state()['messages'][2]['attachments'], [])
        later = self.client.post('/api/document', files={'file': ('later.txt', b'later')}).json()
        with TestClient(app) as other:
            other.post('/api/auth/login', json=LOGIN)
            uploads = {upload['id']: upload['sent'] for upload in self.state(other)['uploads']}
            self.assertEqual(uploads, {item['id']: True, later['id']: False})
            self.assertEqual(self.state(other)['messages'][0]['attachments'][0]['filename'], 'report.txt')

    def test_guest_files_are_sent_with_the_next_message(self):
        with TestClient(app) as guest:
            guest.headers['x-guest-session'] = guest.post('/api/auth/guest').json()['guest_token']
            item = guest.post('/api/document', files={'file': ('guest.txt', b'guest')}).json()
            self.assertEqual(self.send(guest, 'Read it').status_code, 200)
            state = self.state(guest)
            self.assertEqual(state['messages'][0]['attachments'], [{'id': item['id'], 'filename': 'guest.txt'}])
            self.assertTrue(state['uploads'][0]['sent'])
        self.assertEqual(self.database.files, {})

    def test_failed_save_does_not_keep_the_upload(self):
        with patch('app.db.repository.save_file', side_effect=RuntimeError('unavailable')):
            response = self.client.post('/api/document', files={'file': ('notes.txt', b'hello')})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.state()['uploads'], [])


if __name__ == '__main__':
    unittest.main()
