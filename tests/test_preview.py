import io
import json
import os
import unittest
import zipfile
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.services import preview, sessions as registry
from app.services.sessions import Download
from app.tools.create import create_file_tool
from tests.fake_database import mock_database


class PreviewTests(unittest.TestCase):
    def setUp(self):
        registry.sessions.clear()
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(registry.sessions.clear)
        self.database = mock_database(self)
        settings = patch.dict(os.environ, {"LLAMA_CLOUD_API_KEY": "", "EMBEDDING_MODEL": ""})
        settings.start()
        self.addCleanup(settings.stop)

    def create(self, filename, content):
        token = self.client.headers.get('x-guest-session') or self.client.cookies.get('chat_session')
        result = create_file_tool(token).invoke({'filename': filename, 'content': content})
        self.assertIn('Created downloadable file', result)
        return self.client.get('/api/state').json()['generated_files'][-1]

    def get(self, file, client=None, binary=False):
        return (client or self.client).get('/api/files/preview' + ('/content' if binary else ''), params={'file_id': file['id']})

    def test_text_html_are_literal_and_downloads_unchanged_after_reload(self):
        text = '<script>alert(1)</script><h1>Hello / Xin chào</h1>'
        for name in ('notes.md', 'index.html', 'data.json', 'example.py'):
            file = self.create(name, text)
            response = self.get(file)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['text'], text)
            self.assertEqual(response.json()['kind'], 'html' if name.endswith('.html') else 'text')
            self.assertIn('no-store', response.headers['cache-control'])
            self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
            self.assertEqual(self.get(file, binary=True).status_code, 404)
            self.assertEqual(self.client.get('/api/files/download', params={'file_id': file['id']}).content, text.encode())
        self.client.post('/api/auth/logout')
        self.client.post('/api/auth/login', json={'email': 'tester@example.com', 'password': 'test-password-123'})
        self.assertEqual(self.get(file).json()['text'], text)

    def test_office_and_zip_previews(self):
        examples = [
            ('report.docx', 'Hello / Xin chào', 'text'),
            ('budget.xlsx', json.dumps({'sheets': [{'name': 'Tiếng Việt', 'rows': [['Hello', 'Xin chào'], ['formula', '=1+1']]}]}), 'spreadsheet'),
            ('slides.pptx', json.dumps({'slides': [{'title': 'Hello / Xin chào', 'body': 'English / Tiếng Việt'}]}), 'slides'),
            ('bundle.zip', json.dumps({'entries': [{'name': 'README.md', 'content': 'Hello / Xin chào'}]}), 'archive'),
        ]
        for filename, content, kind in examples:
            with self.subTest(filename=filename):
                result = self.get(self.create(filename, content)).json()
                self.assertEqual(result['kind'], kind)
                self.assertFalse(result['truncated'])
                if kind != 'archive':
                    self.assertIn('Xin chào', json.dumps(result, ensure_ascii=False))
        self.assertEqual(result['entries'][0]['name'], 'README.md')
        workbook = Workbook()
        workbook.active['A1'] = '=HYPERLINK("https://example.com", "external")'
        data = io.BytesIO()
        workbook.save(data)
        result = preview.describe(Download('formula.xlsx', data.getvalue()))
        self.assertTrue(result['sheets'][0]['rows'][0][0].startswith('=HYPERLINK'))

    def test_pdf_binary_and_image_have_safe_headers(self):
        file = self.create('report.pdf', 'Hello / Xin chào')
        self.assertEqual(self.get(file).json()['kind'], 'pdf')
        response = self.get(file, binary=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertEqual(response.headers['content-type'], 'application/pdf')
        self.assertIn("default-src 'none'", response.headers['content-security-policy'])
        self.assertEqual(response.headers['content-disposition'], 'attachment')
        self.assertIn('no-store', response.headers['cache-control'])

    def test_limits_corruption_and_unsupported_files(self):
        result = preview.describe(Download('large.txt', b'x' * (preview.MAX_TEXT + 1)))
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['text']), preview.MAX_TEXT)
        with patch('app.services.preview.MAX_BYTES', 5):
            self.assertEqual(preview.describe(Download('large.pdf', b'%PDF-large'))['kind'], 'unsupported')
        for name in ('bad.docx', 'bad.xlsx', 'bad.pptx', 'bad.zip', 'bad.pdf', 'bad.png', 'bad.exe'):
            self.assertEqual(preview.describe(Download(name, b'corrupt'))['kind'], 'unsupported')
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('huge', 'x' * 1000)
        with patch('app.services.preview.MAX_BYTES', 500):
            self.assertEqual(preview.describe(Download('bomb.docx', data.getvalue()))['kind'], 'unsupported')

    def test_account_guest_and_conversation_isolation_for_both_endpoints(self):
        file = self.create('report.pdf', 'Private / Riêng tư')
        conversation = self.client.get('/api/state').json()['conversation_id']
        other = TestClient(app)
        self.addCleanup(other.close)
        for binary in (False, True):
            self.assertEqual(self.get(file, other, binary).status_code, 401)
        other.post('/api/auth/register', json={'name': 'Other', 'email': 'other@example.com', 'password': 'other-password-123'})
        for binary in (False, True):
            self.assertEqual(self.get(file, other, binary).status_code, 404)
        self.client.post('/api/conversations')
        self.assertEqual(self.get(file).status_code, 404)
        self.client.post(f'/api/conversations/{conversation}/select')
        self.assertEqual(self.get(file).status_code, 200)
        other.post('/api/auth/logout')
        guest = other.post('/api/auth/guest').json()['guest_token']
        other.headers['x-guest-session'] = guest
        self.assertEqual(self.get(file, other).status_code, 404)
        self.client.post('/api/auth/logout')
        token = self.client.post('/api/auth/guest').json()['guest_token']
        self.client.headers['x-guest-session'] = token
        with patch('app.db.repository.conversation_files') as database:
            guest_file = self.create('guest.pdf', 'Guest / Khách')
            self.assertEqual(self.get(guest_file).status_code, 200)
            self.assertEqual(self.get(guest_file, binary=True).status_code, 200)
            self.assertEqual(self.get(guest_file, other).status_code, 404)
            self.assertEqual(self.get(guest_file, other, True).status_code, 404)
            database.assert_not_called()

    def test_removed_file_not_exposed_from_stale_session(self):
        file = self.create('report.pdf', 'Private')
        self.database.files.pop(file['id'])
        self.assertEqual(self.get(file).status_code, 404)
        self.assertEqual(self.get(file, binary=True).status_code, 404)
