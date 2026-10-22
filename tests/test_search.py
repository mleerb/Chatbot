import os
import unittest
from unittest.mock import Mock, patch

import httpx
from fastapi.testclient import TestClient

from app.services.agent import make_agent
from app.services.context import conversation_messages
from app.services.sessions import sessions
from app.main import app
from tests.fake_database import mock_database
from app.tools.search import create_search_tool, search_web


class SearchTests(unittest.TestCase):
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

    def test_search_uses_only_question_and_returns_valid_sources(self):
        response = Mock()
        response.json.return_value = {"results": [
            {"title": "Example", "url": "https://example.com/evidence", "content": "Evidence"},
            {"title": "Unsafe", "url": "javascript:alert(1)", "content": "Ignored"},
        ]}
        client = Mock()
        client.post.return_value = response
        client.__enter__ = Mock(return_value=client)
        client.__exit__ = Mock(return_value=False)
        sources = []
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}), patch('app.tools.search.httpx.Client', return_value=client):
            result = create_search_tool('Current user question?', sources).invoke({})
        self.assertIn('https://example.com/evidence', result)
        self.assertEqual(len(sources), 1)
        args, kwargs = client.post.call_args
        self.assertEqual(kwargs['json']['query'], 'Current user question?')
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test-key')
        self.assertNotIn('private file contents', str(kwargs))

    def test_agent_exposes_search_only_when_configured(self):
        with patch('app.services.agent.chat_model', return_value='openai:test'), patch('app.services.agent.create_deep_agent', return_value=object()) as factory:
            with patch.dict(os.environ, {"TAVILY_API_KEY": ""}):
                make_agent('token', 'question', [])
                self.assertEqual(len(factory.call_args.kwargs['tools']), 5)
            with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}):
                make_agent('token', 'question', [])
                self.assertEqual(len(factory.call_args.kwargs['tools']), 6)

    def test_evidence_in_response_and_state_but_not_model_history(self):
        self.client.post('/api/document', files={'file': ('private.md', b'private file contents')})
        def answer(agent, question, history, *args, **kwargs):
            agent.invoke({})
            return 'See evidence.'
        with patch.dict(os.environ, {"TAVILY_API_KEY": "test-key"}), patch('app.services.chat.make_agent', side_effect=lambda token, question, sources: create_search_tool(question, sources)), patch('app.services.chat.answer_question', side_effect=answer), patch('app.tools.search.search_web', return_value=[{'title': 'Source', 'url': 'https://example.com', 'content': 'Result'}]):
            response = self.client.post('/api/chat', json={'message': 'Find external evidence'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['sources'], [{'title': 'Source', 'url': 'https://example.com'}])
        self.assertIn('https://example.com', response.json()['answer'])
        self.assertEqual(response.json()['display_answer'], 'See evidence.')
        state = self.client.get('/api/state').json()
        self.assertEqual(state['messages'][-1]['sources'], response.json()['sources'])
        messages = conversation_messages('Follow up', state['messages'])
        self.assertNotIn('sources', messages[-2])
        self.assertNotIn('Result', str(state))

    def test_search_failure_does_not_create_sources(self):
        sources = []
        with patch('app.tools.search.search_web', side_effect=httpx.TimeoutException('timeout')):
            result = create_search_tool('question', sources).invoke({})
        self.assertIn('failed', result)
        self.assertEqual(sources, [])


if __name__ == '__main__':
    unittest.main()
