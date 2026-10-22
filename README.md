# Aster

A local-first AI chat workspace built with **Next.js, FastAPI, Deep Agents and PostgreSQL**. Ask questions, develop ideas, work with uploaded documents, and download generated files from a light/dark web interface.

> Designed for local use or access through SSH port forwarding. Authentication is included, but this demo is **not hardened for public deployment**.

## Features

- **Accounts and saved conversations:** email/password registration, Argon2id password hashing, and account-scoped history with automatic titles, rename, pin and delete actions.
- **Guest chat:** no registration required. A guest has one temporary chat at a time; starting a new chat deletes the current one and its files. Each browser has a hidden guest token budget (`GUEST_TOKEN_LIMIT`, default 50,000) shared by all its guest tabs; once it is used up, guest chat is blocked in that browser for 24 hours, even after closing the tab, unless the guest logs in or signs up.
- **File context:** read DOCX, UTF-8 text and images with a vision-capable model, or any file type through optional LlamaParse. Upload multiple files and manage them independently.
- **Edits and downloads:** keep uploaded originals, download text/DOCX revisions, and generate text, DOCX, PDF, XLSX, PPTX or ZIP files.
- **Answer formats:** ask for a table, bullet points, steps, code, JSON, or a short or detailed answer in your message, or let the assistant pick what fits. Answers render as Markdown (tables, lists, code with copy) and can be exported as Markdown, Word or PDF from each answer's ⋯ menu.
- **Optional web search:** Tavily evidence links alongside answers.
- **Optional observability:** Langfuse tracing for account chats, with content redacted by default. Guest turns bypass the application's tracing integration.
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
| Uploaded/generated files | Saved in PostgreSQL with the conversation until removed | Temporary and isolated to the guest tab |
| Conversations and usage | Unlimited saved conversations | One chat at a time; `GUEST_TOKEN_LIMIT` tokens per browser, then a 24-hour block |

Closing a guest tab triggers **best-effort** cleanup with a 15-second refresh grace. Browser crashes, restored/duplicated tabs or blocked close requests can delay cleanup. Backend restarts clear all in-memory sessions and files, but not saved account history.

The model provider receives the context needed to answer. Optional search and tracing have their own data-handling policies; server-memory-only guest storage is not a guarantee of zero retention by external providers.

## Configuration

See [`.env.example`](.env.example) and [`.docker.env.example`](.docker.env.example) for the available settings.

- **Model:** `OPENAI_API_KEY`, `CHAT_MODEL` (default `openai:gpt-4o-mini`), and optional `OPENAI_BASE_URL`.
- **Search:** optional `TAVILY_API_KEY`.
- **File parsing:** optional `LLAMA_CLOUD_API_KEY` sends every upload to LlamaParse; `LLAMA_PARSE_TIER` defaults to `cost_effective`.
- **Tracing:** optional `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL`. Keep `LANGFUSE_TRACE_CONTENT=false` to redact exported content.

Provider requests can incur charges. Use an image-capable model for image uploads. See the [setup guide](docs/setup.md#model-and-optional-services) for details.

## Development and validation

Run backend tests in a temporary app container using the built image:

```bash
docker compose run --rm --no-deps --env LLAMA_CLOUD_API_KEY= --volume "$PWD/tests:/app/tests:ro" app python -m unittest discover -s tests
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
- Files under about 6,000 tokens are included in full; larger files are split into pages that the AI reads on demand with outline, page and keyword-search tools (no embeddings or semantic search). The AI sees only the pages it reads, and many small files or very large uploads can still exceed model limits or server memory.
- Login sessions and guest data are in memory. Run a single backend worker; restarting loses them, but not account chats or files.
- Account files are kept in PostgreSQL with no size limit; large uploads grow the database and backups.
- No email verification, password recovery, OAuth or durable login sessions.
- Schema initialization is not a general migration system; future schema changes need explicit migrations.
- AI answers and generated files require review before use.

## Documentation

- [Setup and validation](docs/setup.md): configuration, remote access, backups, commands and testing.
- [File behavior](docs/files.md): supported formats, editing, downloads and storage limits.
- [Architecture](docs/architecture.md): module map, sessions, prompts and integrations.
- Agent rules: `AGENTS.md` holds the overview and commands, `.claude/rules/` the detailed rules and `.agents/skills/` the shared skills. `.claude/CLAUDE.md` imports `AGENTS.md`, `.claude/skills/` links the shared skills, and `.claude/settings.json` sets shared Claude Code permissions; personal overrides go in the uncommitted `.claude/settings.local.json`.
