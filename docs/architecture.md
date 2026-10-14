# Code map

Start at `app/main.py` for FastAPI assembly. Read the relevant group below rather than the entire project.

The project is arranged by responsibility:

```text
app/
  main.py             FastAPI entry point and static serving
  agent.py            Deep Agents setup and turn execution
  model.py            model provider configuration
  context.py          agent message preparation
  prompts.py          Jinja2 template rendering
  prompts/            agent wording
  database.py         PostgreSQL users and messages
  sessions.py         temporary browser state and uploads
  extract.py          uploaded-file extraction
  file_types.py       supported file extensions
  download.py         safe download responses
  trace.py            optional Langfuse tracing
  routers/            HTTP endpoints
  tools/              agent tools
  formats/            generated-file encoders
  static/             HTML, CSS, and compiled browser JavaScript
frontend/             TypeScript browser source
tests/                offline backend tests and database stub
docs/                 behavior and setup guides
```

| Task | Code | Tests |
| --- | --- | --- |
| Chat endpoint, returned citations and state | `app/routers/chat.py` | `tests/test_web.py`, `tests/test_search.py`, `tests/test_users.py` |
| PostgreSQL user and message persistence | `app/database.py`, `app/routers/users.py` | `tests/test_users.py`, `tests/fake_database.py` |
| Upload, original/edited download, removal | `app/routers/documents.py` | `tests/test_web.py`, `tests/test_edit.py` |
| Generated download endpoint | `app/routers/generated.py` | `tests/test_files.py` |
| Browser UI, light/dark theme and glass styling | `app/static/index.html`, `style.css`, `frontend/chat.ts` (built to `app/static/chat.js`) | `tests/test_web.py` |
| Session cookie, upload state and locking | `app/sessions.py` | `tests/test_web.py` |
| Safe download headers | `app/download.py` | `tests/test_web.py`, `tests/test_files.py` |
| Agent invocation and tool registration | `app/agent.py`, `app/tools/__init__.py` | `tests/test_prompts.py`, `tests/test_search.py` |
| User-message composition and response text | `app/context.py` | `tests/test_prompts.py` |
| Uploaded document/image extraction | `app/extract.py` | `tests/test_web.py`, `tests/test_edit.py` |
| Shared file-type allowlists | `app/file_types.py` | `tests/test_files.py`, `tests/test_edit.py`, `tests/test_formats.py` |
| Generated file validation and creation tool | `app/tools/create.py` | `tests/test_files.py`, `tests/test_formats.py` |
| Uploaded file editing tool | `app/tools/edit.py` | `tests/test_edit.py` |
| Tavily search tool | `app/tools/search.py` | `tests/test_search.py` |
| Shared document-block and table validation | `app/formats/blocks.py` | `tests/test_formats.py` |
| File encoders | `app/formats/word.py`, `pdf.py`, `sheet.py`, `slides.py`, `archive.py`; registry in `__init__.py` | `tests/test_formats.py` |
| Provider configuration | `app/model.py` | `tests/test_web.py` |
| Langfuse spans and redaction | `app/trace.py` | `tests/test_trace.py` |
| Agent wording | `app/prompts/*.j2` loaded by `app/prompts.py` | `tests/test_prompts.py` |

The browser UI is branded AGENTslop, with its title using the same display font as the file heading, and is a responsive document workbench: a file shelf and chat pane on desktop, stacked controls on mobile. With no upload, the file status is hidden; the user-selection access warning remains in setup documentation rather than on the page. The attachment button sits beside the chat input and opens the hidden file picker; upload status and file downloads/removal remain in the shelf. `app/static/style.css` holds three RGB brand triplets, theme surfaces, and glass styles. The theme toggle in `frontend/chat.ts` stores the preference locally; it does not send a request to the server. The empty-state headline animates once unless reduced motion is requested. Keep DOM IDs in `index.html` aligned with selectors in `frontend/chat.ts`. Edit the TypeScript source, then run `npm run build`; commit its generated `app/static/chat.js` so FastAPI can serve the app without Node installed on the server.

Flow: browser → `routers/chat.py` → `agent.py` → `tools/__init__.py` → Deep Agents and session-bound tools. Uploads flow through `routers/documents.py` → `extract.py` → in-memory sessions. Generated downloads flow through `routers/generated.py`. The chat API appends retrieved Tavily source URLs to `answer`; the browser uses `display_answer` and separate clickable source links. PostgreSQL stores the plain answer and evidence URLs, not search snippets. Selecting a user loads their last 12 messages for model context and displays their full stored conversation. Browser cookie sessions continue to hold only the active user selection, temporary files and recent model context.

Keep system and document-context wording in Jinja2 templates with `StrictUndefined`; file text is data, never a template. Tool descriptions are API metadata. Keep uploads isolated by session, do not execute binary files or use filesystem tools to modify local files, and never expose this unauthenticated demo publicly. Keep application and test source free of comments and docstrings; update the relevant page in `docs/` when behavior changes. Never print or commit `.env` secrets or private files under `documents/`.
