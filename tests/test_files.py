import io
import unittest
from unittest.mock import patch

from docx import Document

from fastapi.testclient import TestClient

from app.dependencies import sessions
from app.tools.create import create_file_tool, validate_file
from app.main import app


class GeneratedFileTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        sessions.clear()

    def test_generated_file_download_and_restore(self):
        self.assertEqual(self.client.get('/api/files/download').status_code, 404)
        self.client.get('/api/state')
        token = self.client.cookies.get('chat_session')
        session = sessions[token]

        def reply(agent, *args):
            result = agent.invoke({'filename': 'notes.md', 'content': '# Hello\n'})
            self.assertIn('Created downloadable file', result)
            return 'Your file is ready.'

        with patch('app.routers.chat.make_agent', side_effect=lambda token, question, sources: create_file_tool(token)), patch(
            'app.routers.chat.answer_question', side_effect=reply
        ):
            result = self.client.post('/api/chat', json={'message': 'Create notes.md'})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['generated_filename'], 'notes.md')
        self.assertEqual(session.generated_bytes, b'# Hello\n')
        download = self.client.get('/api/files/download')
        self.assertEqual(download.content, b'# Hello\n')
        self.assertIn("filename*=UTF-8''notes.md", download.headers['content-disposition'])
        self.assertEqual(download.headers['x-content-type-options'], 'nosniff')
        self.assertEqual(self.client.get('/api/state').json()['generated_filename'], 'notes.md')
        with TestClient(app) as other:
            self.assertEqual(other.get('/api/files/download').status_code, 404)

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
        self.assertEqual(self.client.get('/api/state').json()['generated_filename'], 'report.docx')

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
