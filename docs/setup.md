# Setup and validation

## Docker Desktop

Run Docker Desktop with Linux containers. On a new machine, from the project root:

```powershell
Copy-Item .env.example .env
```

Do not overwrite an existing `.env`. Edit the new file before starting:

- Set `POSTGRES_PASSWORD` to a long random password, not the example placeholder. `POSTGRES_USER` and `POSTGRES_DB` default to `chatbot`.
- Set `OPENAI_API_KEY`. Leave `OPENAI_BASE_URL` empty for direct OpenAI; configure an HTTPS gateway and its model ID if needed.
- Leave `DATABASE_URL` empty for a new Docker database. The app uses the same `POSTGRES_*` values as PostgreSQL; no URL encoding is needed in `POSTGRES_PASSWORD`.
- Tavily and Langfuse are optional; leave their keys empty when unused. Keep `LANGFUSE_TRACE_CONTENT=false` for redaction.

Compose reads `.env` using its own interpolation rules. Single-quote values containing literal `$` characters; the app's dotenv parser also supports single-quoted values. Never paste real credentials into `.env.example`.

Then run:

```powershell
docker volume create chatbot-postgres-data
docker compose up -d --build
docker compose ps
```

Compose uses the external `chatbot-postgres-data` volume configured directly in `compose.yaml`. The create command above creates it on a new machine or reuses it if it already exists; Compose itself requires this volume to exist. PostgreSQL initializes the requested user/database only when the volume is empty. The app creates its tables after the database becomes healthy. No host Python, uv, or Node.js is required. A model key is needed for chat, not for opening the UI.

Open http://127.0.0.1:8000. `compose.yaml` runs Next.js 16/React 19 on Node.js 24, FastAPI on Python 3.14, and PostgreSQL 16. It waits for database/backend readiness and health-checks all services. Only Next.js (8000) and PostgreSQL (5432) publish local-only ports; FastAPI is internal. Containers run as non-root where applicable and restart with Docker unless explicitly stopped. FastAPI uses a single worker to preserve in-memory browser sessions. Next.js forwards `/api/*`, including cookie and attachment headers, to `http://app:8000`.

### Existing database on this machine

`compose.yaml` preserves the existing external `chatbot-postgres-data` volume directly:

```yaml
volumes:
  postgres_data:
    external: true
    name: chatbot-postgres-data
```

No `compose.override.yaml` is needed. Keep the existing `.env` and its matching `DATABASE_URL`; a non-empty URL takes priority over `POSTGRES_*` settings. Compose still directs the app connection to service `db` on port 5432. Existing data and credentials are unchanged; do not replace them with example values or change the volume name unless intentionally changing databases.

`POSTGRES_*` initializes only an empty volume. Changing these variables later does not change an existing database's passwords, users, or database name. For an existing volume, configure the actual matching credentials. Never remove the volume to resolve a credential mismatch. Do not run another PostgreSQL server against the same volume concurrently.

The previous standalone `chatbot-postgres` container has been left stopped as a fallback. Do not start it while the Compose database is running: both use the same volume and local port. Use `docker compose up -d db` to start only the database for local uv development, and stop the Docker frontend/backend with `docker compose stop frontend app` before running the local development pair. For fallback to the original database container, first run `docker compose down`, then `docker start chatbot-postgres`.

The root `Dockerfile` installs locked backend dependencies using uv on Python 3.14. `frontend/Dockerfile` builds Next.js and copies only its standalone server and static assets into a non-root Node.js runtime. The frontend receives only a backend URL, not the root `.env` or model/database secrets. `.dockerignore` allowlists only app source and dependency files, excluding `.env`, local environments, reports, tests, and private documents from the build context. Compose mounts the existing `.env` read-only at runtime, preserving the application's dotenv parsing. It sets `DATABASE_HOST=db` and `DATABASE_PORT=5432`, and passes the same `POSTGRES_*` settings to both services. `app/db/connection.py` keeps an existing URL's credentials, database name, and connection options; without a URL it builds connection parameters safely from `POSTGRES_*`. The existing local `.env` and uv configuration remain unchanged. Other services running on Windows must use `host.docker.internal` instead of `localhost` in their URLs when accessed from the app container.

Useful commands:

```powershell
docker compose logs --tail 50 -f app
docker compose stop
docker compose up -d
docker compose down
```

Ctrl+C stops following logs, not the containers. `down` without `--volumes` removes this project's containers and network but retains database volumes. The configured external database volume is protected from Compose volume removal, including `docker compose down --volumes` (or `down -v`), but must not be removed manually. Prefer plain `docker compose down` for normal shutdown. Rebuild after source or dependency changes with `docker compose up -d --build`; after `.env` changes, run `docker compose up -d --force-recreate` so interpolated container environment values refresh too. Avoid sharing `docker compose config` output or container inspection output containing credentials. Docker Desktop administrators can access runtime secrets, so this remains a local demo rather than a hardened deployment.

## Optional local development without the app container

On Windows PowerShell, install `uv` if needed with `winget install --id astral-sh.uv -e`, then reopen the terminal. From the project root, run `uv sync --locked`. The project selects Python 3.14 through `.python-version`; uv downloads a compatible interpreter if needed, creates `.venv`, and installs the dependencies recorded in `uv.lock`. No environment activation is needed. The project defines its own uv workspace so it does not inherit an ancestor workspace or share its environment. Local environments are not needed for Docker; `.venv/` is recreated only if you choose this optional workflow.

Use `docker compose up -d db` for the configured database and `docker compose stop frontend app` before running the local frontend/backend pair. With `DATABASE_URL` empty, the host app uses `POSTGRES_*` and connects to `127.0.0.1:5432` by default. Alternatively, create a local PostgreSQL database and set `DATABASE_URL=postgresql://USERNAME:PASSWORD@127.0.0.1:5432/DATABASE` in `.env` (URL-encode special characters in URL credentials). The app creates `chat_users` and `chat_messages` tables and an index at startup; the database user needs schema CREATE privileges. Start `uv run uvicorn app.main:app --host 127.0.0.1 --port 8001`. FastAPI's health and API docs are at http://127.0.0.1:8001/health and http://127.0.0.1:8001/docs. In another terminal, run `npm --prefix frontend ci` then `npm --prefix frontend run dev`. Open http://127.0.0.1:3000 for the UI. The frontend defaults to backend `http://127.0.0.1:8001`; override `BACKEND_URL` in the frontend process environment if needed. This server-only URL must remain trusted and must not contain secrets. Ctrl+C stops each development server.

Manage dependencies with `uv add PACKAGE` and `uv remove PACKAGE`; these update `pyproject.toml` and `uv.lock`. Commit both files and `.python-version`, but not `.venv`. These are the sole Python dependency definitions; the duplicate legacy `requirements.txt` has been removed.

For frontend changes, install Node.js 24 and run `npm --prefix frontend ci`, `npm --prefix frontend run typecheck`, `npm --prefix frontend test`, then `npm --prefix frontend run build` from the project root. Edit `frontend/app/` and `frontend/components/`; there is no generated JavaScript committed under `app/static/`. For a local production frontend after build, run `npm --prefix frontend start`; this copies static assets into the standalone output and binds to `127.0.0.1:3000`. Docker needs no host Node.js. Install browser-test support with `npm --prefix frontend exec -- playwright install chromium`, then run `npm --prefix frontend run test:e2e` after building. Browser tests start an isolated synthetic backend on 8101 and the built standalone frontend on 3100, terminate both afterwards, and never use real credentials, conversations or model APIs.

The root `.env` is loaded by `app/core/config.py` when the application is imported and must not be shared or committed. Set `OPENAI_API_KEY` and optionally `CHAT_MODEL` (default `openai:gpt-4o-mini`) and `OPENAI_BASE_URL` for an HTTPS OpenAI-compatible gateway. With a gateway, the model ID is passed unchanged. Existing shell variables override `.env`; restart after changes. A vision-capable model/gateway is required to analyze uploaded images.

Optional Tavily web search requires `TAVILY_API_KEY` in `.env`. Without it, the web-search tool is not offered to the agent. The search tool sends only the current user question (up to 500 characters) to Tavily, never the uploaded file or its filename. Search is invoked by the agent for external/current evidence, not automatically on every turn. Restart after adding the key; Tavily usage may incur charges. The UI shows web-source links only when Tavily actually returns results.

Optional Langfuse tracing requires `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` (EU `https://cloud.langfuse.com`, US `https://us.cloud.langfuse.com`). Input, output, and prompt content are redacted before export by default; `LANGFUSE_TRACE_CONTENT=true` opts into exporting content. With redaction on, Langfuse can show model usage, tool calls and failures but cannot reveal the question or answer for quality debugging. Do not disable redaction unless authorized to export uploaded content. Chat failures mark the root observation as ERROR with a generic status; private exception details stay out of the status. The model provider still receives readable text or image context. Traces are flushed at shutdown.

Create a user in the browser, select them, and chat; selecting that user again (including after a restart) loads their complete history. Each user has one continuous conversation. Only the last 12 messages are sent to the model. Switching users clears temporary uploads/downloads; uploaded file bytes and generated files are never saved in PostgreSQL. This is not authentication: anyone who can reach the local app can select any user and read their messages. Do not expose it publicly. A working PostgreSQL server is required for runtime startup; tests mock the store and do not exercise a real database.

## Docker validation

After backend changes, rebuild and start the app:

```powershell
docker compose up -d --build
docker compose ps
```

Run offline tests inside a temporary container with the test directory mounted read-only:

```powershell
docker compose run --rm --no-deps --volume "${PWD}/tests:/app/tests:ro" app python -m unittest discover -s tests
```

Smoke-check the Next.js UI and internal FastAPI health/API documentation:

```powershell
curl.exe --fail --silent --output NUL http://127.0.0.1:8000/
docker compose exec -T app python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200; assert urllib.request.urlopen('http://127.0.0.1:8000/docs').status == 200"
```

These commands do not require a host Python environment or `uv run`. The test container uses the same image as the app; database calls are mocked by the offline suite. Tests are excluded from production images and mounted only for validation. Recreating the app clears temporary browser uploads and sessions but retains PostgreSQL users and history.

### Isolated fresh-install check

`tests/compose.yaml` disables published ports and replaces the app's secret mount with `.env.example`. It requires Docker Compose 2.24.4 or newer for `!override`; Docker Desktop's current Compose supports this. It also replaces the external database volume with a disposable project-owned volume. Use both `-f` files and a separate project name so the check never uses the real database:

```powershell
docker compose --env-file .env.example -p chatbot-setup-test -f compose.yaml -f tests/compose.yaml up -d --build --wait
docker compose --env-file .env.example -p chatbot-setup-test -f compose.yaml -f tests/compose.yaml exec -T app python -c "from app.db import repository; assert repository.users() == []; print('Fresh database ready')"
docker compose --env-file .env.example -p chatbot-setup-test -f compose.yaml -f tests/compose.yaml down --volumes
```

The assertion expects the isolated database to be empty on its first run. This stack uses no real model keys and needs no existing volume. Its example password is only for this isolated, unpublished test stack, not for normal use. The scoped cleanup command deletes only the disposable `chatbot-setup-test` stack's project volume; never copy `--volumes` into normal app shutdown commands. The three-service isolated stack was also rebuilt and verified after the Next.js migration: an empty PostgreSQL database, healthy services and the frontend-to-backend state proxy all passed. Writing a synthetic conversation and reading it after restarting the backend/database had also been verified during setup implementation. No real conversation or API call was used for this check.

## Workspace cleanup

`.venv/`, `.venv-win/`, `frontend/node_modules/`, `frontend/.next/`, test reports, TypeScript build info and Python caches are disposable artifacts, not host requirements for Docker. Recreate development dependencies with `uv sync --locked` and `npm --prefix frontend ci`. Keep `frontend/package-lock.json` and `uv.lock`, but do not commit dependency/build directories. `frontend/AGENTS.md` is generated by Next.js for coding-agent guidance and is retained as project guidance. The migration passed Next.js build/type checking, proxy tests, browser tests, the 62-test backend suite in Docker, three-service health checks and live proxy upload/download/isolation checks. No model request or conversation write was needed. Keep source, tests, documentation, dependency manifests and lockfiles, `.env`, `.git/`, and `.agents/`. Existing Word documents under the ignored `reports/` directory were preserved. Never delete PostgreSQL volumes to tidy the workspace. The external database volume is configured in `compose.yaml`; no local override file is required. `.env.example` is safe to commit and contains no real credentials.

## Optional local validation

Validate frontend changes with `npm --prefix frontend run typecheck`, `npm --prefix frontend test`, `npm --prefix frontend run build` and `npm --prefix frontend run test:e2e`, then run `uv run python -m unittest discover -s tests`. Smoke-check `app.main:app` with `uv run python -c "from app.main import app; from fastapi.testclient import TestClient; assert TestClient(app).get('/health').status_code == 200"`. This checks the backend entry point without starting the lifespan or connecting to PostgreSQL; full runtime startup still requires a working database. The import target remains `app.main:app`; `app.main.create_app` is also available as a Uvicorn factory (`uv run uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001`). Tests cover the factory, lifecycle cleanup, unchanged API paths, response schemas, and injectable sessions in `tests/test_app.py`. Local validation requires recreating the optional environment with `uv sync --locked`; use Docker validation if you do not need a host environment.
