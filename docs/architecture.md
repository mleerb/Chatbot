# Code map

Start at `frontend/app/page.tsx` for the landing page, `frontend/app/chat/page.tsx` for the chatbot, and `app/main.py` for FastAPI assembly. Read the relevant group below rather than the entire project.

The project follows a layered FastAPI layout. FastAPI does not mandate one folder structure; these boundaries keep HTTP concerns separate from workflows and persistence without adding an ORM or changing the API.

```text
app/
  main.py             backend factory, lifespan, errors, health endpoint
  dependencies.py     injectable browser-session dependency
  responses.py        safe attachment responses
  core/
    config.py         project paths and root .env loading
    errors.py         service errors mapped to HTTP by main.py
    file_types.py     supported file extensions
    trace.py          optional Langfuse tracing and redaction
  db/
    connection.py     PostgreSQL connection configuration
    repository.py     schema initialization and user/conversation/message queries
  routers/
    __init__.py       central /api router registration
    chat.py           chat and state HTTP endpoints
    conversations.py  conversation create/select/rename/pin/delete endpoints
    documents.py      upload, download, removal HTTP endpoints
    generated.py      generated-file download HTTP endpoint
    users.py          user and history HTTP endpoints
  schemas/
    chat.py           chat, state, message, citation models
    documents.py      upload and removal response models
    users.py          user request and response models
    conversations.py  conversation and update models
  services/
    agent.py          Deep Agents creation and turn execution
    chat.py           chat workflow, citations, persistence
    context.py        agent message preparation
    documents.py      in-memory upload/download/removal operations
    extract.py        uploaded-file text/image extraction
    model.py          model provider configuration
    sessions.py       temporary browser state and locking
    users.py          user selection and history workflows
    conversations.py  conversation ownership, selection and management
  prompts.py          Jinja2 template rendering
  prompts/            agent wording
  tools/              session-bound agent tools
  formats/            generated-file encoders
frontend/
  app/                Next.js App Router pages, global CSS, /api/* route
  components/         chat orchestration, users, messages, files, composer
  lib/                API types/client, streaming backend proxy
  tests/              proxy and source-link tests
  e2e/                isolated browser tests with a synthetic backend
  Dockerfile          Next.js standalone image
tests/                offline backend tests and database stub
docs/                 behavior and setup guides
```

`create_app()` returns a new FastAPI application; `app = create_app()` preserves the `app.main:app` entry point. The lifespan initializes PostgreSQL and flushes traces in a `finally` block at shutdown. `core/config.py` loads the root `.env` before routers and agent integrations are imported; paths do not depend on the current working directory.

Routers handle HTTP parsing, response models, and attachment responses. `dependencies.py` supplies `(token, ChatSession)` through `Depends`, retaining cookie flags, expiry, capacity limits, and session isolation. Tests can replace it through `app.dependency_overrides[session_for]`. Services own locking and workflows, use `db/repository.py` for persistence, and raise `ServiceError` rather than importing FastAPI. The application translates those errors to the existing status codes and `{"detail": ...}` responses. Synchronous endpoints run in FastAPI's worker pool; asynchronous upload reading offloads extraction and state changes to a worker. Response schemas document JSON results in `/docs`; all existing `/api` URLs remain unchanged. Binary downloads continue to use explicit responses rather than JSON schemas.

| Task | Code | Tests |
| --- | --- | --- |
| Chat endpoint, returned citations and state | `app/routers/chat.py`, `app/services/chat.py`, `app/schemas/chat.py` | `tests/test_web.py`, `tests/test_search.py`, `tests/test_users.py` |
| Conversation creation, selection, rename, pin and deletion | `app/routers/conversations.py`, `app/services/conversations.py`, `app/db/repository.py` | `tests/test_conversations.py`, `frontend/e2e/chat.spec.ts` |
| PostgreSQL user/message persistence and connection overrides | `app/db/connection.py`, `app/db/repository.py`, `app/services/users.py` | `tests/test_database.py`, `tests/test_users.py`, `tests/fake_database.py` |
| Upload, original/edited download, removal | `app/routers/documents.py`, `app/services/documents.py` | `tests/test_web.py`, `tests/test_edit.py` |
| Generated download endpoint | `app/routers/generated.py` | `tests/test_files.py` |
| Landing page, preview, navigation and responsive layout | `frontend/app/page.tsx`, `frontend/app/landing.css` | `frontend/e2e/landing.spec.ts` |
| Browser UI, theme, users, messages, in-chat files | `frontend/components/`, `frontend/app/globals.css` | `frontend/e2e/chat.spec.ts` |
| Streaming API proxy, cookies and attachment headers | `frontend/app/api/[...path]/route.ts`, `frontend/lib/proxy.ts` | `frontend/tests/proxy.test.ts` |
| Session cookie, upload state and locking | `app/dependencies.py`, `app/services/sessions.py` | `tests/test_app.py`, `tests/test_web.py` |
| Safe download headers | `app/responses.py` | `tests/test_web.py`, `tests/test_files.py` |
| Agent invocation and tool registration | `app/services/agent.py`, `app/tools/__init__.py` | `tests/test_prompts.py`, `tests/test_search.py` |
| User-message composition and response text | `app/services/context.py` | `tests/test_prompts.py` |
| Uploaded document/image extraction | `app/services/extract.py` | `tests/test_web.py`, `tests/test_edit.py` |
| Shared file-type allowlists | `app/core/file_types.py` | `tests/test_files.py`, `tests/test_edit.py`, `tests/test_formats.py` |
| Generated file validation and creation tool | `app/tools/create.py` | `tests/test_files.py`, `tests/test_formats.py` |
| Uploaded file editing tool | `app/tools/edit.py` | `tests/test_edit.py` |
| Tavily search tool | `app/tools/search.py` | `tests/test_search.py` |
| Shared document-block and table validation | `app/formats/blocks.py` | `tests/test_formats.py` |
| File encoders | `app/formats/word.py`, `pdf.py`, `sheet.py`, `slides.py`, `archive.py`; registry in `__init__.py` | `tests/test_formats.py` |
| Provider configuration | `app/services/model.py` | `tests/test_web.py` |
| Langfuse spans and redaction | `app/core/trace.py` | `tests/test_trace.py` |
| Application assembly, lifespan, schemas, dependency injection | `app/main.py`, `app/dependencies.py`, `app/routers/__init__.py`, `app/schemas/` | `tests/test_app.py` |
| Agent wording | `app/prompts/*.j2` loaded by `app/prompts.py` | `tests/test_prompts.py` |

The browser UI is a Next.js App Router application with React and TypeScript. It uses a professional purple palette with light/dark tokens, locally bundled IBM Plex Sans, flat surfaces and a restrained sidebar/chat layout rather than glass, gradients or decorative headlines. Shared canvas, hover, shadow and focus-ring tokens keep the landing page, light workspace and dark workspace consistent. `components/brand.tsx` renders a shared wordmark with a heavier AGENT, lighter purple slop and a decorative dot. Larger responsive wordmarks anchor the landing hero and empty chat, while compact versions identify the navigation and sidebar. Typography takes inspiration from restrained product interfaces such as Linear and Raycast without importing their assets, palettes or templates. Subtle elevation distinguishes the landing preview and composer; border-light conversation rows, numbered workflow markers, compact file cards and branded assistant avatars clarify hierarchy without changing the layout. Focus treatments and hover transitions respect reduced motion; browser screenshots disable animations for stable theme capture. The sidebar holds user selection/creation, the current user's conversation list and the theme control. `components/conversations.tsx` provides new-chat creation, selection, inline rename, pin/unpin and delete confirmation. `components/actions.tsx` hides Rename, Pin/Unpin and Delete in a three-dot disclosure at the right of each conversation name. The dropdown supports Tab navigation, closes on outside clicks or focus leaving it, and restores trigger focus on Escape without closing the mobile sidebar. Pinned conversations sort first, with newest IDs first within each group. Names and pin state are persisted in PostgreSQL. Deletion cascades to messages; deleting the active chat clears temporary files and selects the first remaining chat, or leaves an empty workspace if none remain. Sending a message or uploading a file in an empty workspace creates a conversation. Existing legacy messages are migrated into one conversation per user at startup; repeated initialization does not duplicate them. On mobile, a native modal dialog provides focus trapping, Escape dismissal and focus restoration; on desktop it is a non-modal sidebar. The main column has a conversation header, independently scrolling chat and a fixed composer. `frontend/app/layout.tsx` owns metadata and loads `globals.css`; `/` renders a static server-component landing page from `page.tsx` with route-specific `landing.css`, while `chat/page.tsx` renders the client-side chat component at `/chat`. The landing page shares purple color tokens and bundled IBM Plex Sans with the app, and uses a compact hero, a small illustrative chat preview, three short workflow steps and workspace links. The simplified layout omits feature panels, format strips, secondary navigation and repeated calls to action. Landing copy, metadata and the chat header present a general-purpose AI agent for questions, brainstorming, writing and planning; file uploads are optional context, not the starting point. The illustrative preview demonstrates planning a project without attachments. The preview is clearly labeled and contains only synthetic content; landing visits do not initialize browser sessions or call backend APIs. Landing styles are scoped and responsive down to 320px, with a skip link and reduced-motion support. The chatbot keeps its existing light/dark preference and behavior. `components/chat.tsx` manages initialization, requests and browser state; `people.tsx`, `messages.tsx`, `files.tsx` and `composer.tsx` own focused UI sections; `icon.tsx` centralizes small functional SVG icons. Theme preference stays in localStorage. The composer supports multiline input, Enter to send, Shift+Enter for a new line, and visible chips for all active attachments. Upload originals, every edited revision and generated downloads appear in the scrolling conversation area, never in the sidebar. This is a session file collection, not a persisted attachment-to-message relationship: after reload the current collection is recovered from `/api/state`, and after session expiry the files are no longer available. File removal works from either the in-chat file entry or composer chip. The mobile drawer has a short opening animation; other workspace transitions are limited to color, border and shadow changes, respecting reduced motion. English empty/error/status text helps users choose a user and start chatting. Messages and filenames render as React text, not HTML; source links allow only HTTP/HTTPS. The frontend initializes the session before further requests, preventing parallel first requests from creating different cookies. File selection uploads sequentially.

`frontend/app/api/[...path]/route.ts` forwards API methods through `lib/proxy.ts` to the server-only `BACKEND_URL`. It streams request and response bodies without multipart parsing or a proxy file-size cap, forwards session cookies and attachment headers, strips hop-by-hop headers, disables caching, and returns a generic 502 for connection failures. The fixed backend origin is never supplied by the browser. No API keys or root `.env` are passed to the frontend. FastAPI no longer serves `/` or static assets; `/health` is its internal health endpoint and `/docs` remains available internally.

Flow: browser → Next.js `/api/*` proxy → `routers/chat.py` → `services/chat.py` → `services/agent.py` → `tools/__init__.py` → Deep Agents and session-bound tools. Uploads flow through `routers/documents.py` → `services/documents.py` → `services/extract.py` → in-memory sessions. Generated downloads flow through `routers/generated.py` → `services/documents.py` → `responses.py`. The chat API appends retrieved Tavily source URLs to `answer`; the browser uses `display_answer` and separate clickable source links. PostgreSQL stores the plain answer and evidence URLs, not search snippets. Selecting a user opens their most recent pinned conversation, or their newest conversation if none are pinned, and creates a conversation when they have none. Selecting a conversation loads its last 12 messages for model context and displays its full stored history. Browser cookie sessions hold only the active user/conversation selection, temporary files and recent model context. Switching conversations or users clears files. Conversation endpoints scope every operation to the session's selected user; foreign or missing IDs return 404. `/api/state` includes `conversation_id` and `conversations` alongside messages and files. `/api/users/{user_id}/messages` remains a compatibility endpoint returning the selected user's combined history; the browser uses conversation-scoped state. State/chat requests discard stale context if another session deleted the active conversation. `services/sessions.py` stores uploads by unique ID, each with its original bytes and an ordered list of immutable edited revisions, plus a separate collection of generated files. Duplicate filenames do not replace files. Context includes all uploads with filename/ID metadata from `prompts/upload.j2`; editing selects an upload by ID. State/chat responses expose only file collections (`uploads`, `generated_files`), not legacy top-level single-file metadata. Download/delete endpoints accept session-scoped IDs; download requests without an ID still select the latest file. Agent execution and context preparation use one multi-upload path rather than separate single-file parameters. `frontend/components/chat.tsx` uploads multi-selections sequentially and renders independent download links for every original, revision and generated output. There are no application-enforced file-count or download-count limits; memory and model context remain finite. `tests/test_uploads.py` covers retention, targeting, revision downloads, duplicate names, removal and session isolation.

Docker deployment uses separate backend/frontend Dockerfiles and allowlisted build contexts, `compose.yaml`, and the credential-free `.env.example`; see `docs/setup.md`. Next.js runs as a non-root Node.js 24 standalone service, serves the UI at `127.0.0.1:8000`, and proxies to the internal FastAPI service. FastAPI runs one worker to retain session ownership. PostgreSQL remains bound to local port 5432 for optional host development. Node dependencies and Next output live only in the frontend image; root model/database secrets are mounted only into FastAPI. The base Compose file uses the external `chatbot-postgres-data` volume directly, with no local override file. Create the volume before first startup on a new machine; PostgreSQL initializes an empty volume from `POSTGRES_*`. Database configuration prefers an existing `DATABASE_URL`, otherwise builds connection parameters from `POSTGRES_*`; Compose overrides host/port for container networking. `tests/compose.yaml` replaces the external volume with a project-owned test volume for isolated empty-volume validation without real secrets or published ports.

Keep system and document-context wording in Jinja2 templates with `StrictUndefined`; file text is data, never a template. Tool descriptions are API metadata. Keep uploads isolated by session, do not execute binary files or use filesystem tools to modify local files, and never expose this unauthenticated demo publicly. Keep application and test source free of comments and docstrings; update the relevant page in `docs/` when behavior changes. Never print or commit `.env` secrets or private files under `documents/`.
