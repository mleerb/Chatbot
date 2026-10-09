import io
import unittest
from unittest.mock import patch

from docx import Document
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import sessions


def word_file(text: str) -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    output = io.BytesIO()
    doc.save(output)
    return output.getvalue()


class WebTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        sessions.clear()

    def test_page_upload_chat_and_remove(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertIn('Document Chat', self.client.get('/').text)
        with patch('app.routers.chat.make_agent', return_value=object()), patch(
            'app.routers.chat.answer_question', return_value='Found it'
        ) as answer:
            uploaded = word_file('Private note')
            response = self.client.post('/api/document', files={
                'file': ('note.docx', uploaded,
                         'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['filename'], 'note.docx')
            download = self.client.get('/api/document/download')
            self.assertEqual(download.content, uploaded)
            self.assertIn('attachment;', download.headers['content-disposition'])
            self.assertEqual(download.headers['x-content-type-options'], 'nosniff')
            self.assertEqual(self.client.post('/api/chat', json={'message': 'What does it say?'}).json(),
                             {'answer': 'Found it', 'display_answer': 'Found it',
                              'generated_filename': '', 'edited_filename': '', 'sources': []})
            self.assertEqual(answer.call_args.args[4], 'Private note')
            self.assertEqual(answer.call_args.args[6], 'note.docx')
            state = self.client.get('/api/state').json()
            self.assertEqual(len(state['messages']), 2)
            self.assertEqual(state['messages'][1]['sources'], [])
            self.assertNotIn('Private note', str(state))
            self.assertEqual(self.client.delete('/api/document').status_code, 200)
            self.assertEqual(self.client.get('/api/state').json()['filename'], '')
            self.assertEqual(self.client.get('/api/document/download').status_code, 404)

    def test_sessions_are_isolated(self):
        with TestClient(app) as another:
            self.client.post('/api/document', files={'file': ('one.docx', word_file('Only A'))})
            self.assertEqual(another.get('/api/state').json()['filename'], '')
            self.assertEqual(self.client.get('/api/state').json()['filename'], 'one.docx')

    def test_large_text_and_markdown_upload(self):
        text = b'# Heading\n' + b'a' * 1_000_001
        response = self.client.post('/api/document', files={'file': ('big.md', text)})
        self.assertEqual(response.status_code, 200)
        self.assertIn('First 20,000 characters', response.json()['status'])
        self.assertEqual(self.client.get('/api/state').json()['filename'], 'big.md')
        self.assertEqual(len(next(iter(sessions.values())).document), 20_000)

    def test_binary_upload_is_accepted_but_not_interpreted(self):
        response = self.client.post('/api/document', files={'file': ('program.exe', b'MZ' + b'X' * 1_000_001)})
        self.assertEqual(response.status_code, 200)
        self.assertIn('cannot be analyzed', response.json()['status'])
        session = next(iter(sessions.values()))
        self.assertEqual(session.document, '')
        self.assertEqual(session.image_url, '')
        self.assertEqual(session.filename, 'program.exe')
        download = self.client.get('/api/document/download')
        self.assertEqual(download.content, b'MZ' + b'X' * 1_000_001)
        self.assertEqual(download.headers['content-type'], 'application/octet-stream')
        self.assertIn('filename*=UTF-8\'\'program.exe', download.headers['content-disposition'])
        self.assertNotIn('MZ', str(self.client.get('/api/state').json()))

    def test_image_upload_provides_vision_context(self):
        from PIL import Image
        image = io.BytesIO()
        Image.new('RGB', (2, 2), 'red').save(image, format='PNG')
        response = self.client.post('/api/document', files={'file': ('photo.png', image.getvalue())})
        self.assertEqual(response.status_code, 200)
        self.assertIn('vision-capable', response.json()['status'])
        self.assertTrue(next(iter(sessions.values())).image_url.startswith('data:image/jpeg;base64,'))
        with patch('app.routers.chat.make_agent', return_value=object()), patch(
            'app.routers.chat.answer_question', return_value='A red image'
        ) as answer:
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Describe it'}).status_code, 200)
            self.assertTrue(answer.call_args.args[5].startswith('data:image/jpeg;base64,'))
            self.assertEqual(answer.call_args.args[6], 'photo.png')

    def test_replacement_and_session_isolation_of_downloads(self):
        self.assertEqual(self.client.get('/api/document/download').status_code, 404)
        with TestClient(app) as another:
            self.client.post('/api/document', files={'file': ('a.txt', b'first')})
            self.assertEqual(another.get('/api/document/download').status_code, 404)
            another.post('/api/document', files={'file': ('b.txt', b'other')})
            self.assertEqual(another.get('/api/document/download').content, b'other')
            self.client.post('/api/document', files={'file': ('replacement.txt', b'second')})
            self.assertEqual(self.client.get('/api/document/download').content, b'second')
            self.client.delete('/api/document')
            self.assertEqual(self.client.get('/api/document/download').status_code, 404)
            self.assertEqual(another.get('/api/document/download').content, b'other')

    def test_empty_file_and_download_name_are_preserved(self):
        response = self.client.post('/api/document', files={'file': ('empty.md', b'')})
        self.assertEqual(response.status_code, 200)
        self.assertIn('no readable text', response.json()['status'])
        download = self.client.get('/api/document/download')
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b'')
        self.assertIn("filename*=UTF-8''empty.md", download.headers['content-disposition'])

    def test_invalid_files_are_accepted_without_false_claims(self):
        response = self.client.post('/api/document', files={'file': ('bad.docx', b'invalid')})
        self.assertEqual(response.status_code, 200)
        self.assertIn('Could not extract', response.json()['status'])
        self.assertEqual(self.client.post('/api/chat', json={'message': '  '}).status_code, 422)


if __name__ == '__main__':
    unittest.main()
