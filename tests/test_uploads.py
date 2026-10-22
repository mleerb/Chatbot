import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.context import conversation_messages
from app.services.sessions import sessions
from app.tools.create import create_file_tool
from app.tools.edit import create_edit_tool
from tests.fake_database import mock_database


class UploadTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)
        mock_database(self)
        self.title = patch('app.services.title.generate', return_value='')
        self.title.start()
        self.addCleanup(self.title.stop)
        self.client.get('/api/state')
        self.token = self.client.cookies.get('chat_session')

    def tearDown(self):
        self.client.close()
        sessions.clear()

    def upload(self, name, data):
        response = self.client.post('/api/document', files={'file': (name, data)})
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_state_and_reply_use_file_collections_only(self):
        self.upload('note.txt', b'content')
        state = self.client.get('/api/state').json()
        with patch('app.services.chat.make_agent'), patch(
            'app.services.chat.answer_question', return_value='Ready',
        ):
            response = self.client.post('/api/chat', json={'message': 'Hello'})
        self.assertEqual(response.status_code, 200)
        for result in (state, response.json()):
            self.assertEqual(len(result['uploads']), 1)
            self.assertEqual(result['generated_files'], [])
            for field in ('filename', 'status', 'generated_filename', 'edited_filename'):
                self.assertNotIn(field, result)

    def test_many_uploads_and_duplicate_names_have_independent_downloads(self):
        items = [self.upload('same.txt', str(index).encode()) for index in range(25)]
        self.assertEqual(len({item['id'] for item in items}), 25)
        self.assertEqual(len(self.client.get('/api/state').json()['uploads']), 25)
        for index, item in enumerate(items):
            for _ in range(2):
                response = self.client.get('/api/document/download', params={'file_id': item['id']})
                self.assertEqual(response.content, str(index).encode())
        self.assertNotIn('document', self.client.get('/api/state').json()['uploads'][0])

    def test_edits_target_ids_and_keep_every_revision(self):
        first = self.upload('same.txt', b'old first')
        second = self.upload('same.txt', b'old second')
        tool = create_edit_tool(self.token)
        self.assertIn('multiple files', tool.invoke({'old_text': 'old', 'new_text': 'new'}))
        for item in (first, second):
            for old, new in [('old', 'new'), ('new', 'final')]:
                self.assertIn('Edited copy ready', tool.invoke({
                    'file_id': item['id'], 'old_text': old, 'new_text': new,
                }))
        for item in self.client.get('/api/state').json()['uploads']:
            self.assertEqual(len(item['edits']), 2)
            for revision, prefix in zip(item['edits'], (b'new', b'final')):
                for _ in range(3):
                    response = self.client.get('/api/document/edited', params={
                        'file_id': item['id'], 'revision_id': revision['id'],
                    })
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.content.startswith(prefix))
            original = self.client.get('/api/document/download', params={'file_id': item['id']})
            self.assertTrue(original.content.startswith(b'old'))
        self.upload('third.txt', b'extra')
        self.assertEqual(len(self.client.get('/api/state').json()['uploads'][0]['edits']), 2)

    def test_remove_one_and_isolation(self):
        first = self.upload('a.txt', b'first')
        second = self.upload('b.txt', b'second')
        with TestClient(app) as other:
            other.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
            self.assertEqual(other.get('/api/document/download', params={'file_id': first['id']}).content, b'first')
            self.assertEqual(other.get('/api/document/edited', params={'file_id': first['id']}).status_code, 404)
        self.assertEqual(self.client.delete('/api/document', params={'file_id': first['id']}).status_code, 200)
        self.assertEqual(self.client.get('/api/document/download', params={'file_id': first['id']}).status_code, 404)
        self.assertEqual(self.client.get('/api/document/download', params={'file_id': second['id']}).content, b'second')
        self.assertEqual(self.client.delete('/api/document', params={'file_id': 'missing'}).status_code, 404)
        self.client.delete('/api/document')
        self.assertEqual(self.client.get('/api/state').json()['uploads'], [])

    def test_all_contexts_include_ids_and_treat_template_text_as_data(self):
        first = self.upload('one.txt', b'First {{ private }}')
        second = self.upload('two.txt', b'Second')
        session = sessions[self.token]
        messages = conversation_messages('Compare them', [], uploads=list(session.uploads.values()))
        content = str(messages)
        for value in (first['id'], second['id'], 'one.txt', 'two.txt', 'First {{ private }}', 'Second'):
            self.assertIn(value, content)
        self.assertEqual(messages[-1], {'role': 'user', 'content': 'Compare them'})
        with patch('app.services.chat.make_agent'), patch('app.services.chat.answer_question', return_value='Compared') as answer:
            response = self.client.post('/api/chat', json={'message': 'Compare them'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(answer.call_args.kwargs['uploads']), 2)

    def test_generated_files_are_retained_even_with_identical_names(self):
        tool = create_file_tool(self.token)
        for index in range(5):
            tool.invoke({'filename': 'output.txt', 'content': str(index)})
        files = self.client.get('/api/state').json()['generated_files']
        self.assertEqual(len(files), 5)
        for index, item in enumerate(files):
            response = self.client.get('/api/files/download', params={'file_id': item['id']})
            self.assertEqual(response.content, str(index).encode())
        self.assertEqual(self.client.get('/api/files/download', params={'file_id': 'missing'}).status_code, 404)
        with TestClient(app) as other:
            other.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
            self.assertEqual(other.get('/api/files/download', params={'file_id': files[0]['id']}).content, b'0')
        self.client.post('/api/auth/register', json={'name': 'Another', 'email': 'another@example.com', 'password': 'test-password-123'})
        state = self.client.get('/api/state').json()
        self.assertEqual(state['generated_files'], [])
        self.assertEqual(state['uploads'], [])

    def test_revisions_survive_a_failed_chat_turn(self):
        item = self.upload('note.txt', b'old')

        def fail(agent, *args, **kwargs):
            result = agent.invoke({'file_id': item['id'], 'old_text': 'old', 'new_text': 'new'})
            self.assertIn('Edited copy ready', result)
            raise RuntimeError('Model failed after editing')

        with patch('app.services.chat.make_agent', return_value=create_edit_tool(self.token)), patch(
            'app.services.chat.answer_question', side_effect=fail,
        ), self.assertLogs('app.services.chat', level='ERROR'):
            response = self.client.post('/api/chat', json={'message': 'Edit this file'})
        self.assertEqual(response.status_code, 502)
        state = self.client.get('/api/state').json()
        revision = state['uploads'][0]['edits'][0]
        self.assertEqual(self.client.get('/api/document/edited', params={
            'file_id': item['id'], 'revision_id': revision['id'],
        }).content, b'new')

    def test_invalid_edit_ids_do_not_change_any_file(self):
        first = self.upload('one.txt', b'old')
        tool = create_edit_tool(self.token)
        self.assertIn('not found', tool.invoke({'file_id': 'missing', 'old_text': 'old', 'new_text': 'new'}))
        tool.invoke({'file_id': first['id'], 'old_text': 'old', 'new_text': 'new'})
        second = self.upload('two.txt', b'other')
        revision = self.client.get('/api/state').json()['uploads'][0]['edits'][0]['id']
        self.assertEqual(self.client.get('/api/document/edited', params={
            'file_id': second['id'], 'revision_id': revision,
        }).status_code, 404)


if __name__ == '__main__':
    unittest.main()
