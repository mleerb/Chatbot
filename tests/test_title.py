import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.prompts import render_prompt
from app.services import title
from app.services.sessions import sessions
from tests.fake_database import mock_database


class TitleTests(unittest.TestCase):
    def test_clean_removes_labels_quotes_and_markdown(self):
        self.assertEqual(title.clean('Title: "Planning a Trip to Hanoi."\nExtra line'), 'Planning a Trip to Hanoi')
        self.assertEqual(title.clean('## **Budget Review**'), 'Budget Review')
        self.assertEqual(title.clean('   '), '')

    def test_long_titles_are_shortened_at_word_boundary(self):
        result = title.clean('word ' * 30)
        self.assertLessEqual(len(result), title.MAX_TITLE + 1)
        self.assertTrue(result.endswith('word…'))

    def test_fallback_uses_question(self):
        self.assertEqual(title.fallback('  How   do I bake bread?  '), 'How do I bake bread?')
        self.assertTrue(title.fallback('a ' * 60).endswith('…'))
        self.assertEqual(title.fallback(''), 'New conversation')

    def test_prompt_treats_messages_as_data(self):
        prompt = render_prompt('title.j2', question='{{ secret }}', answer='Reply')
        self.assertIn('<user_message>\n{{ secret }}\n</user_message>', prompt)
        self.assertIn('<assistant_reply>\nReply\n</assistant_reply>', prompt)
        self.assertIn('at most 6 words', prompt)

    def test_generate_calls_model_with_rendered_prompt(self):
        model = MagicMock()
        model.invoke.return_value = SimpleNamespace(content='"Bread Baking Basics"')
        with patch('app.services.title.chat_model', return_value=model):
            self.assertEqual(title.generate('How do I bake bread?', 'x' * 5000), 'Bread Baking Basics')
        prompt = model.invoke.call_args.args[0][0].content
        self.assertIn('How do I bake bread?', prompt)
        self.assertIn('x' * title.MAX_EXCERPT, prompt)
        self.assertNotIn('x' * (title.MAX_EXCERPT + 1), prompt)

    def test_suggest_falls_back_when_model_fails_or_is_empty(self):
        with patch('app.services.title.generate', side_effect=RuntimeError('offline')):
            self.assertEqual(title.suggest('Explain tides', 'Answer'), 'Explain tides')
        with patch('app.services.title.generate', return_value=''):
            self.assertEqual(title.suggest('Explain tides', 'Answer'), 'Explain tides')


class AutoTitleTests(unittest.TestCase):
    def setUp(self):
        sessions.clear()
        self.client = TestClient(app)
        self.database = mock_database(self)

    def tearDown(self):
        self.client.close()
        sessions.clear()

    def send(self, question, generated='Generated title'):
        with patch('app.services.chat.make_agent', return_value=object()), patch(
            'app.services.chat.answer_question', return_value='Answer'
        ), patch('app.services.title.generate', return_value=generated) as generate:
            response = self.client.post('/api/chat', json={'message': question})
        self.assertEqual(response.status_code, 200)
        return generate

    def active_title(self):
        state = self.client.get('/api/state').json()
        return next(chat['title'] for chat in state['conversations'] if chat['id'] == state['conversation_id'])

    def test_account_conversation_is_named_once_after_first_turn(self):
        self.send('First question')
        self.assertEqual(self.active_title(), 'Generated title')
        generate = self.send('Second question', 'Other title')
        generate.assert_not_called()
        self.assertEqual(self.active_title(), 'Generated title')

    def test_account_rename_is_kept(self):
        conversation = self.client.get('/api/state').json()['conversation_id']
        self.client.patch(f'/api/conversations/{conversation}', json={'title': 'My name'})
        self.send('First question')
        self.assertEqual(self.active_title(), 'My name')
        self.client.patch(f'/api/conversations/{conversation}', json={'title': 'Changed later'})
        self.assertEqual(self.active_title(), 'Changed later')

    def test_failed_save_does_not_name_conversation(self):
        with patch('app.services.chat.make_agent', return_value=object()), patch(
            'app.services.chat.answer_question', return_value='Answer'
        ), patch('app.db.repository.save_turn', side_effect=RuntimeError('unavailable')), patch(
            'app.services.title.generate'
        ) as generate:
            self.assertEqual(self.client.post('/api/chat', json={'message': 'Question'}).status_code, 503)
        generate.assert_not_called()

    def test_guest_chat_is_named_and_can_be_renamed(self):
        self.client.post('/api/auth/logout')
        self.client.headers['x-guest-session'] = self.client.post('/api/auth/guest').json()['guest_token']
        self.send('Guest question')
        self.assertEqual(self.active_title(), 'Generated title')
        conversation = self.client.get('/api/state').json()['conversation_id']
        self.client.patch(f'/api/conversations/{conversation}', json={'title': 'Guest name'})
        self.assertEqual(self.active_title(), 'Guest name')
        second = self.client.post('/api/conversations').json()['id']
        self.client.patch(f'/api/conversations/{second}', json={'title': 'Named first'})
        generate = self.send('Another question')
        generate.assert_not_called()
        self.assertEqual(self.active_title(), 'Named first')


if __name__ == '__main__':
    unittest.main()
