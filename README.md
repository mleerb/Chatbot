# AGENTslop

Local Next.js + FastAPI chatbot with Deep Agents, PostgreSQL-backed users and chat history, browser-session uploads, downloadable generated documents, and optional Tavily web evidence.

The backend uses a layered FastAPI layout: `app/routers/` for HTTP endpoints, `app/schemas/` for API models, `app/services/` for workflows, `app/db/` for persistence, and `app/core/` for configuration and tracing. `app/main.py` assembles the app; `app/dependencies.py` provides browser sessions. See [architecture](docs/architecture.md) for the full map.

## Run with Docker Desktop

On a new machine, start Docker Desktop with Linux containers. From the project root:

```powershell
Copy-Item .env.example .env
```

Edit `.env`: replace `POSTGRES_PASSWORD` with a long random password and set `OPENAI_API_KEY`. Keep `DATABASE_URL` empty for a new Docker database. Then run:

```powershell
docker volume create chatbot-postgres-data
docker compose up -d --build
```

Open http://127.0.0.1:8000. Check status with `docker compose ps`, follow app logs with `docker compose logs -f app`, and stop with `docker compose down`. Compose uses the external `chatbot-postgres-data` volume; the create command above reuses it if it already exists. PostgreSQL initializes a database only when the volume is empty. The app mounts your local `.env` read-only; neither credentials nor user documents are included in the image. The volume configuration is included directly in `compose.yaml`; no override file is needed. Do not overwrite an existing `.env`. See [setup](docs/setup.md) for initial setup, existing data, and optional local development.

Docker runs three services: Next.js frontend, FastAPI backend, and PostgreSQL. No host Python or Node.js is needed. Python dependencies are locked in `uv.lock`; frontend dependencies are locked in `frontend/package-lock.json`.

The Next.js App Router frontend lives in `frontend/app/`, with React components in `frontend/components/`. The English UI uses a purple light/dark palette, a user sidebar and in-chat files, with active attachment chips above the composer. Its `/api/*` proxy streams uploads/downloads to FastAPI and preserves browser-session cookies. The public local address remains http://127.0.0.1:8000; FastAPI has no published Docker port. See [setup](docs/setup.md) for frontend development and validation. Do not expose this unauthenticated demo publicly.

## Read only what you need

- [Setup and validation](docs/setup.md): PostgreSQL, model/Tavily configuration, tests, smoke check.
- [File behavior](docs/files.md): uploads, downloads, generation, and practical limits.
- [Architecture](docs/architecture.md): module map, prompts, sessions, and tracing.
