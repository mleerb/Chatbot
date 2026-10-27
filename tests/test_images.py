import base64
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import guest, images, quota
from app.services.sessions import Download, sessions
from app.tools import tools_for_turn
from app.tools.image import create_image_tool, image_filename
from tests.fake_database import mock_database

PNG = images.PNG + b"image-bytes"


class ImageTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        guest.meters.clear()
        self.addCleanup(guest.meters.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.addCleanup(sessions.clear)
        self.database = mock_database(self)
        self.title = patch('app.services.title.generate', return_value='')
        self.title.start()
        self.addCleanup(self.title.stop)
        self.client.get('/api/state')
        self.token = self.client.cookies.get('chat_session')

    def draw(self, calls=1, generate=None, client=None, token=None):
        token = token or self.token
        outputs = []

        def reply(agent, *args, **kwargs):
            for index in range(calls):
                outputs.append(agent.invoke({'prompt': 'A watercolor cat', 'filename': f'cat {index}.png'}))
            return 'Here is your cat.'

        with patch('app.services.images.generate', **(generate or {'return_value': PNG})) as provider, patch(
            'app.services.chat.make_agent', side_effect=lambda token, question, sources: create_image_tool(token)
        ), patch('app.services.chat.answer_question', side_effect=reply):
            response = (client or self.client).post('/api/chat', json={'message': 'Draw a cat'})
        return response, outputs, provider

    def test_created_image_is_attached_to_the_answer_and_viewable(self):
        response, outputs, provider = self.draw()
        self.assertEqual(response.status_code, 200)
        self.assertIn('Created image cat-0.png', outputs[0])
        provider.assert_called_once_with('A watercolor cat', None)
        attachments = response.json()['attachments']
        self.assertEqual([item['filename'] for item in attachments], ['cat-0.png'])
        state = self.client.get('/api/state').json()
        self.assertEqual(state['messages'][-1]['attachments'], attachments)
        self.assertEqual(state['messages'][0]['attachments'], [])
        self.assertEqual(state['generated_files'], attachments)
        view = self.client.get('/api/files/view', params={'file_id': attachments[0]['id']})
        self.assertEqual(view.status_code, 200)
        self.assertEqual(view.content, PNG)
        self.assertEqual(view.headers['content-type'], 'image/png')
        self.assertEqual(view.headers['x-content-type-options'], 'nosniff')
        self.assertIn("default-src 'none'", view.headers['content-security-policy'])
        self.assertTrue(view.headers['content-disposition'].startswith('inline'))
        self.assertEqual(self.client.get('/api/files/download', params={'file_id': attachments[0]['id']}).content, PNG)
        self.assertEqual(self.database.usages[1]['images'], 1)
        self.assertEqual(self.database.files[attachments[0]['id']]['kind'], 'generated')

    def test_view_serves_only_generated_png_images(self):
        session = sessions[self.token]
        text = Download('notes.png', b'not really a png')
        session.generated[text.id] = text
        self.assertEqual(self.client.get('/api/files/view', params={'file_id': text.id}).status_code, 404)
        self.assertEqual(self.client.get('/api/files/view', params={'file_id': 'missing'}).status_code, 404)
        with TestClient(app) as other:
            other.post('/api/auth/register', json={'name': 'Other', 'email': 'other@example.com', 'password': 'test-password-123'})
            response, _, _ = self.draw()
            image = response.json()['attachments'][0]['id']
            self.assertEqual(other.get('/api/files/view', params={'file_id': image}).status_code, 404)

    def test_account_image_limit_and_failures_do_not_use_the_quota(self):
        with patch('app.services.quota.IMAGE_LIMIT', 2):
            _, outputs, provider = self.draw(calls=3)
            self.assertEqual(provider.call_count, 2)
            self.assertEqual(outputs[2], quota.IMAGE_LIMIT_MESSAGE)
            self.assertEqual(self.database.usages[1]['images'], 2)
            with patch('app.services.quota.now', return_value=quota.next_midnight()):
                _, outputs, _ = self.draw(generate={'side_effect': RuntimeError('provider down')})
                self.assertIn('Image generation failed', outputs[0])
                self.assertEqual(self.database.usages[1]['images'], 0)
                with patch('app.services.storage.save_generated', side_effect=RuntimeError('database down')):
                    _, outputs, _ = self.draw()
                self.assertIn('Could not save the image', outputs[0])
                self.assertEqual(self.database.usages[1]['images'], 0)
                response, outputs, _ = self.draw()
                self.assertEqual(len(response.json()['attachments']), 1)
                self.assertEqual(self.database.usages[1]['images'], 1)

    def test_guest_image_limit_is_per_browser(self):
        with TestClient(app) as visitor:
            visitor.post('/api/auth/logout')
            started = visitor.post('/api/auth/guest').json()
            visitor.headers['x-guest-session'] = started['guest_token']
            response, outputs, provider = self.draw(calls=3, client=visitor, token=started['guest_token'])
            self.assertEqual(provider.call_count, guest.GUEST_IMAGE_LIMIT)
            self.assertEqual(outputs[-1], quota.IMAGE_LIMIT_MESSAGE)
            images_made = response.json()['attachments']
            self.assertEqual(len(images_made), 2)
            self.assertEqual(visitor.get('/api/files/view', params={'file_id': images_made[0]['id']}).content, PNG)
            self.assertEqual(guest.meters[sessions[started['guest_token']].guest_meter].images, 2)
            self.assertEqual(guest.GUEST_IMAGE_LIMIT, 2)
        self.assertNotIn(1, self.database.usages)

    def test_tool_is_offered_only_when_configured(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key", "IMAGE_MODEL": "gpt-image-2.5-flare", "TAVILY_API_KEY": ""}):
            self.assertIn('generate_image', [item.name for item in tools_for_turn('token', 'q', [])])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key", "IMAGE_MODEL": "", "TAVILY_API_KEY": ""}):
            self.assertNotIn('generate_image', [item.name for item in tools_for_turn('token', 'q', [])])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "IMAGE_MODEL": "gpt-image-2.5-flare", "TAVILY_API_KEY": ""}):
            self.assertNotIn('generate_image', [item.name for item in tools_for_turn('token', 'q', [])])
        with patch.dict(os.environ, {"OPENAI_API_KEY": "key", "TAVILY_API_KEY": ""}):
            os.environ.pop("IMAGE_MODEL", None)
            self.assertFalse(images.available())
            self.assertNotIn('generate_image', [item.name for item in tools_for_turn('token', 'q', [])])

    def test_filenames_are_sanitized(self):
        self.assertEqual(image_filename('Watercolor Cat!.PNG'), 'Watercolor-Cat.png')
        self.assertEqual(image_filename('../../etc/passwd'), 'etc-passwd.png')
        self.assertEqual(image_filename('***'), 'image.png')
        self.assertEqual(image_filename('a' * 100 + '.png'), 'a' * 60 + '.png')


class ProviderTests(unittest.TestCase):
    def provider(self, data=PNG):
        client = MagicMock()
        client.images.generate.return_value = SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(data).decode())])
        return client

    def test_generate_uses_settings_and_returns_png_bytes(self):
        client = self.provider()
        environment = {"IMAGE_MODEL": "gpt-image-2.5-sunburst", "IMAGE_QUALITY": "low", "IMAGE_SIZE": "1536x1024"}
        with patch.dict(os.environ, environment), patch('app.services.images.client', return_value=client):
            self.assertEqual(images.generate('A lighthouse'), PNG)
            self.assertEqual(images.generate('A lighthouse', '1024x1536'), PNG)
        first, second = client.images.generate.call_args_list
        self.assertEqual(first.kwargs, {'model': 'gpt-image-2.5-sunburst', 'prompt': 'A lighthouse', 'size': '1536x1024',
                                        'quality': 'low', 'output_format': 'png', 'n': 1})
        self.assertEqual(second.kwargs['size'], '1024x1536')

    def test_defaults_and_validation(self):
        client = self.provider()
        with patch.dict(os.environ, {"IMAGE_MODEL": "gpt-image-2.5-flare", "IMAGE_QUALITY": "", "IMAGE_SIZE": "999x999"}):
            with patch('app.services.images.client', return_value=client):
                images.generate('A lighthouse', '5x5')
        self.assertEqual(client.images.generate.call_args.kwargs['model'], 'gpt-image-2.5-flare')
        self.assertEqual(client.images.generate.call_args.kwargs['size'], '1024x1024')
        self.assertEqual(client.images.generate.call_args.kwargs['quality'], 'medium')
        with patch('app.services.images.client', return_value=self.provider(b'GIF89a')):
            with self.assertRaises(ValueError):
                images.generate('A lighthouse')
        with patch.dict(os.environ, {"OPENAI_BASE_URL": "http://insecure.example"}):
            with self.assertRaises(ValueError):
                images.client()
