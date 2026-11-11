import io
import unittest
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from app.services.sessions import sessions
from app.tools.create import create_file_tool, validate_file
from tests.fake_database import mock_database


class GeneratedFileTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)
        mock_database(self)
        self.title = patch('app.services.title.generate', return_value='')
        self.title.start()
        self.addCleanup(self.title.stop)

    def tearDown(self):
        self.client.close()
        sessions.clear()

    def test_generated_file_download_and_restore(self):
        self.assertEqual(self.client.get('/api/files/download').status_code, 404)
        self.client.get('/api/state')
        token = self.client.cookies.get('chat_session')
        session = sessions[token]

        def reply(agent, *args, **kwargs):
            result = agent.invoke({'filename': 'notes.md', 'content': '# Hello\n'})
            self.assertIn('Created downloadable file', result)
            return 'Your file is ready.'

        with patch('app.services.chat.make_agent', side_effect=lambda token, question, sources: create_file_tool(token)), patch(
            'app.services.chat.answer_question', side_effect=reply
        ):
            result = self.client.post('/api/chat', json={'message': 'Create notes.md'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['generated_files'][0]['filename'], 'notes.md')
        self.assertEqual(session.latest_generated.data, b'# Hello\n')
        download = self.client.get('/api/files/download')
        self.assertEqual(download.content, b'# Hello\n')
        self.assertIn("filename*=UTF-8''notes.md", download.headers['content-disposition'])
        self.assertEqual(download.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(self.client.get('/api/state').json()['generated_files'][0]['filename'], 'notes.md')
        with TestClient(app) as other:
            other.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
            self.assertEqual(other.get('/api/files/download').content, b'# Hello\n')

    def test_standalone_text_files_through_chat_download_and_reload(self):
        examples = {
            'index.html': '<!doctype html><h1>Hello / Xin chào</h1><script>alert(1)</script>',
            'README.md': '# Hello / Xin chào\n\nStandalone Markdown.',
            'data.json': '{"english":"Hello","vietnamese":"Xin chào"}',
            'data.csv': 'language,greeting\nen,Hello\nvi,Xin chào\n',
            'example.py': 'print("Hello / Xin chào")\n',
        }
        for filename, content in examples.items():
            with self.subTest(filename=filename):
                def reply(agent, *args, filename=filename, content=content, **kwargs):
                    result = agent.invoke({'filename': filename, 'content': content})
                    self.assertIn('Created downloadable file', result)
                    return 'File ready / Tệp đã sẵn sàng.'

                with patch('app.services.chat.make_agent', side_effect=lambda token, question, sources: create_file_tool(token)), patch(
                    'app.services.chat.answer_question', side_effect=reply
                ):
                    response = self.client.post('/api/chat', json={
                        'message': f'Create a standalone downloadable {filename}. Tạo tệp riêng, không dùng ZIP.'})
                self.assertEqual(response.status_code, 200)
                generated = response.json()['generated_files'][-1]
                self.assertEqual(generated['filename'], filename)
                download = self.client.get('/api/files/download', params={'file_id': generated['id']})
                self.assertEqual(download.content, content.encode('utf-8'))
                self.assertFalse(download.content.startswith(b'PK\\x03\\x04'))
                self.assertIn('attachment;', download.headers['content-disposition'])
                self.assertIn(filename, download.headers['content-disposition'])
                self.assertEqual(download.headers['x-content-type-options'], 'nosniff')
                self.assertTrue(download.headers['content-type'].startswith('application/octet-stream'))
        stored = self.client.get('/api/state').json()['generated_files']
        self.assertEqual([item['filename'] for item in stored], list(examples))
        self.client.post('/api/auth/logout')
        self.client.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
        for item in self.client.get('/api/state').json()['generated_files']:
            self.assertEqual(self.client.get('/api/files/download', params={'file_id': item['id']}).content,
                             examples[item['filename']].encode('utf-8'))

    def test_all_supported_text_extensions_are_individual_utf8_files(self):
        from app.core.file_types import TEXT_EXTENSIONS

        for extension in sorted(TEXT_EXTENSIONS):
            with self.subTest(extension=extension):
                filename, data = validate_file('example' + extension, 'Hello / Xin chào')
                self.assertEqual(filename, 'example' + extension)
                self.assertEqual(data, 'Hello / Xin chào'.encode())

    def test_invalid_extensions_paths_and_large_outputs(self):
        for filename in ('../bad.md', 'dir/file.txt', r'dir\\file.txt', 'program.exe', 'image.png', ''):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                validate_file(filename, 'content')
        large = 'x' * 1_000_001
        self.assertEqual(validate_file('large.txt', large), ('large.txt', large.encode('utf-8')))
        self.assertEqual(validate_file('hello.json', '{"ok": true}'), ('hello.json', b'{"ok": true}'))

    def test_large_generated_file_can_be_downloaded(self):
        self.client.get('/api/state')
        token = self.client.cookies.get('chat_session')
        content = 'x' * 1_000_001
        result = create_file_tool(token).invoke({'filename': 'large.txt', 'content': content})
        self.assertIn('Created downloadable file', result)
        self.assertEqual(self.client.get('/api/files/download').content, content.encode('utf-8'))

    def test_creates_real_docx_and_downloads_it(self):
        self.client.get('/api/state')
        token = self.client.cookies.get('chat_session')
        result = create_file_tool(token).invoke({'filename': 'report.docx', 'content': 'First line\nSecond line'})
        self.assertIn('Created downloadable file', result)
        download = self.client.get('/api/files/download')
        self.assertEqual(download.status_code, 200)
        self.assertIn("filename*=UTF-8''report.docx", download.headers['content-disposition'])
        document = Document(io.BytesIO(download.content))
        self.assertEqual([paragraph.text for paragraph in document.paragraphs], ['First line', 'Second line'])
        self.assertEqual(self.client.get('/api/state').json()['generated_files'][0]['filename'], 'report.docx')

    def test_tool_rejects_unsafe_output_without_overwriting(self):
        self.client.get('/api/state')
        token = self.client.cookies.get('chat_session')
        tool = create_file_tool(token)
        tool.invoke({'filename': 'ok.txt', 'content': 'good'})
        result = tool.invoke({'filename': 'malware.exe', 'content': 'bad'})
        self.assertIn('Unsupported format', result)
        self.assertEqual(self.client.get('/api/files/download').content, b'good')


if __name__ == '__main__':
    unittest.main()
