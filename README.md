# Aster

A local-first AI chat workspace built with **Next.js, FastAPI, Deep Agents and PostgreSQL**. Ask questions, develop ideas, work with uploaded documents, and download generated files from a light/dark web interface.

> Designed for local use or access through SSH port forwarding. Authentication is included, but this demo is **not hardened for public deployment**.

## Features

- **Accounts and saved conversations:** email/password registration, Argon2id password hashing, and account-scoped history with automatic titles, rename, pin and delete actions.
- **Guest chat:** no registration required. A guest has one temporary chat at a time; starting a new chat deletes the current one and its files. Each browser has a hidden guest token budget (`GUEST_TOKEN_LIMIT`, default 50,000) shared by all its guest tabs; once it is used up, guest chat is blocked in that browser until midnight, even after closing the tab, unless the guest logs in or signs up.
- **Daily account limit:** each account can use `USER_TOKEN_LIMIT` tokens (default 500,000) per day. Once it is used up, chat and uploads pause until midnight and the workspace shows when they reopen; saved conversations stay readable. Each account and each guest browser can also upload `UPLOAD_LIMIT` files a day (default 5). All guest and account limits reset at 00:00 in `LIMIT_TIMEZONE` (default `Asia/Ho_Chi_Minh`).
- **New upload limits:** configurable defaults of 20 MiB per file, 20 original files and 100 MiB of original upload data per conversation. Limits reject new uploads only; existing files are preserved. Provider timeouts are configurable with slow-network defaults. See [completion status](docs/completion.md).
- **File context:** read DOCX, UTF-8 text and images with a vision-capable model, or any file type through optional LlamaParse. Upload multiple files and manage them independently.
- **Storage and recovery:** operator-only storage reports, private database/workspace backups, isolated PostgreSQL restore verification and explicit-ID snapshot cleanup with dry-run and typed confirmation. No automatic deletion; see [storage guide](docs/storage.md).
- **Upload inspection (opt-in):** export new account uploads to a private, Git-ignored `.workspace/` folder with extracted text, exact split chunks, source labels and processing results. Guest exports require the separate `WORKSPACE_EXPORT_GUESTS=true` opt-in. This machine enables both through a private Compose override, so guest upload text also persists on disk. See [workspace setup](docs/setup.md#upload-inspection-workspace) before enabling; these debug copies persist independently of app file deletion.
- **Edits and downloads:** keep uploaded originals, download text/DOCX revisions, and generate standalone text/code/data files (`.txt`, `.md`, `.csv`, `.json`, `.xml`, `.yaml`, `.yml`, `.html`, `.css`, `.js`, `.py`, `.log`, `.ini`), DOCX, PDF, XLSX or PPTX. Each requested file has its own download; ZIP is used only when an archive is explicitly requested.
- **Preview before download:** generated files have separate Preview and Download actions. HTML offers an isolated static visual preview and escaped source; PDFs render locally with page navigation/zoom; Office files show extracted text or sheet values, ZIP shows entries, and PNG shows the image. Previews are bounded and never execute file scripts or formulas.
- **Image generation (optional, off by default):** set `IMAGE_MODEL` to an image model your OpenAI key or gateway offers, and the assistant can create PNG images that appear under its answer, limited to `IMAGE_LIMIT` (default 10) per account and `GUEST_IMAGE_LIMIT` (default 2) per guest browser a day.
- **Upload guidance and recovery:** File help shows configured limits and parsing support; files show queued/processing and ready/warning states with expandable details. Retry or dismiss individual failed uploads without resending successful files or losing your draft.
- **Live answers:** answers appear word by word while the model writes, with a short note when the assistant searches the web, reads or edits a file, or creates a file or image. **Stop** ends an answer early and keeps what was written, marked *Stopped*.
- **Answer controls:** copy any message or answer, edit one of your messages to resend it (this replaces it and everything after it), regenerate the last answer, and rate answers with Good answer / Bad answer. With Langfuse tracing on, ratings on account answers are also sent as a feedback score.
- **Answer formats:** ask for a table, bullet points, steps, code, JSON, or a short or detailed answer in your message, or let the assistant pick what fits. Answers render as Markdown (tables, lists, code with copy) and can be exported as Markdown, Word or PDF from each answer's ⋯ menu.
- **Document citations and source viewer:** clickable `[D1]` references open the exact extracted section/page text supplied to the assistant, including small files and edited revisions. Sources display only escaped plain text in a desktop side panel or mobile sheet. References are validated against supplied context, not automatically fact-checked.
- **Optional web search:** Tavily evidence links use separate `[W1]` markers and a Web sources group, distinct from Document sources.
- **Optional observability:** Langfuse tracing for account chats, with content redacted by default. Model calls are named `generate-response`; routine history-patching and parent-notifier middleware observations are omitted unless they fail. Tool calls and structural nesting remain visible. Automatic HTTP and internal FastAPI spans are disabled, so healthchecks and polling do not consume tracing quota. `LANGFUSE_EXCLUDED_ROUTES=/*` excludes all automatic request telemetry by default, without disabling explicit chat tracing or feedback scores. Guest turns bypass the application's tracing integration.
- **Responsive interface:** Aster landing page and chat workspace, light/dark themes, and locally served fonts with no external CDN dependency.

## Quick start

### Requirements

- Git and Docker with Docker Compose v2.24.4 or newer.
- An OpenAI API key or credentials for a compatible provider.
- Available local port **18080**.

Docker supplies Node.js, Python and PostgreSQL; host installations are not required to run the app.

### Fresh installation

**For a new installation only.** If you already have configuration or database data, keep it and follow the [setup guide](docs/setup.md) instead of replacing files or credentials.

```bash
git clone https://github.com/mleerb/Chatbot.git
cd Chatbot
cp .env.example .env
cp .docker.env.example .docker.env
chmod 600 .env .docker.env
```

Edit the private configuration files before starting:

| File | Required configuration |
| --- | --- |
| `.env` | Set `OPENAI_API_KEY`. Optionally change `CHAT_MODEL` and `OPENAI_BASE_URL`. |
| `.docker.env` | Replace `POSTGRES_PASSWORD` with a long, random password. This file overrides the example database password in `.env`. |

Never commit either private file. The example files contain placeholders only.

Create the external database volume and start the stack:

```bash
docker volume create chatbot_postgres_data
docker compose up -d --build --wait
docker compose ps
```

Open **http://127.0.0.1:18080/** and select **Start a conversation**. Create an account to save history, or choose **Continue as guest**.

The stack uses **PostgreSQL 17**. An existing volume must have compatible data and matching credentials; changing an environment variable does not change an existing database password. Do not delete the volume or change the PostgreSQL major version to resolve startup errors.

### Access from another computer

When the app runs on a Linux server, use VS Code Remote SSH port forwarding for server port **18080**, then open the forwarded address shown in the Ports panel. The local port may differ from the server port.

For a manual SSH alternative, see [remote access](docs/setup.md#open-from-your-computer-through-ssh). Keep the server bound to loopback; do not expose the app publicly.

## How it works

```text
Browser → Next.js frontend and API proxy → FastAPI / Deep Agents
                                               ├─ Model provider
                                               ├─ PostgreSQL: account history
                                               └─ Server memory: sessions and files
```

Only the frontend publishes a host port, bound to `127.0.0.1:18080`. FastAPI and PostgreSQL stay inside the Docker network. PostgreSQL access uses SQLAlchemy ORM over Psycopg.

### Accounts, guests and privacy

| | Account | Guest |
| --- | --- | --- |
| Chat history | Saved in PostgreSQL | Server memory only; never imported into accounts |
| Access lifetime | 12-hour idle session; log in again after restart | No idle timeout; normally ends when the chat tab closes |
| Uploaded/generated files | Saved in PostgreSQL with the conversation until removed | Temporary and isolated to the guest tab; opt-in upload inspection copies persist separately |
| Conversations and usage | Unlimited saved conversations; `USER_TOKEN_LIMIT` tokens per day, reset at midnight | One chat at a time; `GUEST_TOKEN_LIMIT` tokens per browser per day, reset at midnight |

Closing a guest tab triggers **best-effort** cleanup with a 15-second refresh grace. Browser crashes, restored/duplicated tabs or blocked close requests can delay cleanup. Backend restarts clear all in-memory sessions and files, but not saved account history.

The model provider receives the context needed to answer. Optional search and tracing have their own data-handling policies; server-memory-only guest storage is not a guarantee of zero retention by external providers.

## Configuration

See [`.env.example`](.env.example) and [`.docker.env.example`](.docker.env.example) for the available settings.

- **Model:** `OPENAI_API_KEY`, `CHAT_MODEL` (default `openai:gpt-4o-mini`), and optional `OPENAI_BASE_URL`.
- **Search:** optional `TAVILY_API_KEY`.
- **File parsing:** optional `LLAMA_CLOUD_API_KEY` sends every upload to LlamaParse; `LLAMA_PARSE_TIER` defaults to `cost_effective`.
- **Upload inspection:** `WORKSPACE_EXPORT_ENABLED=false` by default; `WORKSPACE_EXPORT_GUESTS=false` by default; `WORKSPACE_EXPORT_DIR` selects a private export directory. This machine's ignored `compose.override.yaml` enables both exports automatically for normal Compose commands. The optional `compose.workspace.yaml` mounts `.workspace/` for host inspection.
- **Tracing:** optional `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL`. Keep `LANGFUSE_TRACE_CONTENT=false` to redact exported content.

Provider requests can incur charges. Use an image-capable model for image uploads. See the [setup guide](docs/setup.md#model-and-optional-services) for details.

## Document-workflow readiness

The [final acceptance](docs/acceptance.md) completed regression, live tracing-redaction read-back and a zero-observation health window. **Live account content tracing remains enabled on this machine**; redaction was verified only with content disabled in isolated workers. Persistent guest/account inspection copies also remain enabled by operator choice. No public-ready or fully private deployment claim is made.

The [document acceptance audit](docs/document-audit.md) verified eight live synthetic chat cases, including long-PDF citations, Vietnamese text, scanned-PDF OCR, missing information and conversation isolation. **Semantic retrieval is currently blocked on this machine:** the configured embedding gateway rejects `text-embedding-3-small` with HTTP 400, so long-file search falls back to keywords. Choose a compatible embedding configuration and revalidate before treating multilingual semantic search as ready.

## Development and validation

Run backend tests in a temporary app container using the built image:

```bash
docker compose run --rm --no-deps --env LLAMA_CLOUD_API_KEY= --env EMBEDDING_MODEL= --volume "$PWD/scripts:/app/scripts:ro" --volume "$PWD/tests:/app/tests:ro" app python -m unittest discover -s tests
```

Optional PostgreSQL integration tests require a **separate disposable database**. Never point them at your saved application data.

For frontend checks, use Node.js 24:

```bash
npm --prefix frontend ci
npm --prefix frontend run build
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

E2E tests use a synthetic backend, not real provider credentials. To check the running deployment's landing page, guest entry and refresh without calling the model, run `npm --prefix frontend run test:live`.

## Limitations

- Without `LLAMA_CLOUD_API_KEY`, uploaded PDF, XLSX and PPTX contents are **not extracted**. With it, uploads leave the server for LlamaParse and are billed per page.
- Files under about 6,000 tokens are included in full; larger files use outline, page and hybrid-search tools. Hybrid search combines meaning and keyword rankings in memory, returns the best 5 pages across the conversation's large files, and falls back to keywords when embeddings are unavailable. `EMBEDDING_MODEL` defaults to `text-embedding-3-small`; set it empty to disable external embedding calls. Large-file pages and search queries go to the configured OpenAI-compatible provider (including first-search backfill of old files). Account vectors persist with the file; guest vectors stay in RAM. Embedding tokens are billed separately and do not count against chat limits. No pgvector is required. Many small files or very large uploads can still exceed model limits or server memory.
- Login sessions and guest data are in memory, except guest upload text/chunk snapshots when explicitly enabled. Run a single backend worker; restarting loses guest sessions but not account files or inspection copies.
- Original uploads have per-file/conversation admission limits; revisions, generated files, extracted content, vectors and workspace snapshots do not have a comprehensive storage quota yet. Saved files grow the database and backups.
- No email verification, password recovery, OAuth or durable login sessions.
- Schema initialization is not a general migration system; future schema changes need explicit migrations.
- AI answers and generated files require review before use.

## Documentation

- [Setup and validation](docs/setup.md): configuration, remote access, backups, commands and testing.
- [Final acceptance](docs/acceptance.md): checked flows, Langfuse redaction/health evidence and remaining limitations.
- [Storage and recovery](docs/storage.md): operator reports, private backups, disposable restore verification and safe manual snapshot cleanup.
- [File behavior](docs/files.md): supported formats, editing, downloads and storage limits.
- [Architecture](docs/architecture.md): module map, sessions, prompts and integrations.
- Agent rules: `AGENTS.md` holds the overview and commands, `.claude/rules/` the detailed rules and `.agents/skills/` the shared skills. `.claude/CLAUDE.md` imports `AGENTS.md`, `.claude/skills/` links the shared skills, and `.claude/settings.json` sets shared Claude Code permissions; personal overrides go in the uncommitted `.claude/settings.local.json`.
