import unittest
from unittest.mock import patch

from jinja2 import UndefinedError

from app.services.agent import make_agent
from app.services.context import conversation_messages
from app.prompts import render_prompt
from app.services.sessions import Upload


class PromptTests(unittest.TestCase):
    def test_system_prompt_is_loaded_from_template(self):
        with patch("app.services.agent.chat_model", return_value="openai:test"), patch(
            "app.services.agent.create_deep_agent", return_value=object()
        ) as create_agent:
            make_agent()
        self.assertEqual(
            create_agent.call_args.kwargs["system_prompt"], render_prompt("system.j2")
        )
        self.assertIn("untrusted user-provided data", render_prompt("system.j2"))
        self.assertIn("create_text_file", render_prompt("system.j2"))
        self.assertIn("edit_uploaded_file", render_prompt("system.j2"))
        self.assertIn("Choose the format from the\nuser's request", render_prompt("system.j2"))
        self.assertIn("Markdown", render_prompt("system.j2"))
        self.assertIn("Never send file", render_prompt("system.j2"))

    def test_document_template_renders_all_text_literally(self):
        document = "Literal {{ not_a_variable }} " + "x" * 20_001 + " END"
        upload = Upload("note.txt", b"", document, "", "Ready")
        messages = conversation_messages("Summarize", [], [upload])
        self.assertEqual(len(messages), 3)
        content = messages[1]["content"]
        self.assertIn("{{ not_a_variable }}", content)
        self.assertEqual(content.split("<document>\n", 1)[1].split("\n</document>", 1)[0], document)
        self.assertEqual(messages[-1], {"role": "user", "content": "Summarize"})

    def test_image_and_unreadable_file_messages(self):
        upload = Upload('photo.png', b'', '', 'data:image/jpeg;base64,abc', 'Ready')
        image = conversation_messages("What's in it?", [], [upload])
        self.assertEqual(image[1]['content'][1]['image_url']['url'], 'data:image/jpeg;base64,abc')
        self.assertIn('photo.png', image[1]['content'][0]['text'])
        upload = Upload('sample.exe', b'', '', '', 'Unreadable')
        unknown = conversation_messages('What is it?', [], [upload])
        self.assertIn('not available to analyze', unknown[1]['content'])
        self.assertIn('sample.exe', unknown[1]['content'])

    def test_missing_template_variable_fails(self):
        with self.assertRaises(UndefinedError):
            render_prompt("document.j2")


if __name__ == "__main__":
    unittest.main()
