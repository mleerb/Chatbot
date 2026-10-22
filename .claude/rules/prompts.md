---
paths:
  - "app/prompts/**"
  - "app/prompts.py"
  - "app/services/**"
  - "tests/**"
---

# Prompt rules

- Store **all system prompt instructions and other agent prompt wording** in dedicated Jinja2 files under `app/prompts/`, never in Python string literals. `app/prompts/system.j2` holds the system prompt and `app/prompts/document.j2` holds the document-context message.
- Load and render templates via `app/prompts.py` using Jinja2 with `StrictUndefined`, so missing variables fail visibly. Pass only intended variables; treat uploaded document text as data, never as a template to render.
- When adding or changing prompts, update the templates rather than hard-coding instructions in `app/services/agent.py` or `app/services/context.py`, and add or update tests for the rendered result.
