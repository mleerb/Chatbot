# Setup and validation

## Run on this Linux computer

The stack is configured for `/home/minh/leminh/chatbot` on this machine:

- Homepage: http://127.0.0.1:18080
- Chat workspace: http://127.0.0.1:18080/chat
- Frontend: Next.js on Node.js 24, serving the standalone Aster landing page and the existing chat workspace.
- Backend: FastAPI on Python 3.14, using SQLAlchemy ORM and the Psycopg driver.
- Database: PostgreSQL 17, using the existing external Docker volume `chatbot_postgres_data`.
- Only the frontend publishes a host port. FastAPI and PostgreSQL are accessible only inside the Compose network. Port 18080 is this project's existing port; other applications and their ports are not modified.

From the project root:

```bash
docker compose up -d --build --wait
docker compose ps
```

Open the homepage and choose **Start a conversation**. Both the landing page and workspace now use Aster branding, Inter typography and matching lavender-glass light/dark themes. The landing page is simplified to a hero, features and three FAQ answers, with no pricing section. `/chat` offers login, registration, or **Continue as guest** for a temporary chat. If old assets appear after deployment, confirm port 18080 and refresh.

The standard command above now needs no `--env-file` argument and no local Compose override. It replaces the old backend-only `chatbot:local` deployment with separate frontend/backend services. FastAPI runs one worker to preserve ownership of in-memory sessions. Health checks gate frontend startup on backend readiness and backend startup on PostgreSQL readiness.

## Open from your computer through SSH

The application stays on the Linux server. Prefer the existing VS Code Remote SSH forwarding when it works; a separate manual SSH tunnel is optional, not required. No project-specific VS Code settings are required. Use the Ports panel's Forwarded Address or Open in Browser action for remote port 18080. Do not infer the mapping from a terminal link alone.

For an optional fixed manual tunnel, the mapping is:

```text
Browser on your computer: http://127.0.0.1:18081/
  → SSH tunnel
    → dev2:127.0.0.1:18080
      → Aster frontend and internal backend/database
```

Use only one forwarding method. If choosing the optional manual tunnel below, first stop the VS Code forward for this project in the Ports panel. Do not stop unrelated applications or forwards. Otherwise keep the working VS Code forward and skip the manual-tunnel instructions.

On your own computer, not in the remote `minh@dev2` terminal, start:

```bash
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:18081:127.0.0.1:18080 minh@dev2
```

Use the same host alias, port and identity options as your normal SSH connection if different. Keep the terminal open, then manually type `http://127.0.0.1:18081/` into your browser. Avoid opening terminal links through VS Code if it rewrites them to a different forwarded port. The server still uses 18080; only your computer uses 18081. No Docker port change or public listener is needed.

If an existing tunnel on 18081 works, reuse it. If SSH reports that 18081 is already in use, do not launch repeated tunnels or automatically kill the listener. Check whether it is the existing tunnel and close only a confirmed stale connection before retrying. Close the tunnel with Ctrl+C when finished. A dropped tunnel does not stop the server, but the browser address will be unavailable until it is started again.

On the server, confirm startup without rebuilding unchanged images:

```bash
docker compose up -d --wait
docker compose ps
curl --fail --silent --output /dev/null http://127.0.0.1:18080/
```

## Private configuration

Keep both private files in the project root:

- `.env`: model-provider settings and optional Tavily/Langfuse settings.
- `.docker.env`: `POSTGRES_PASSWORD` matching the existing PostgreSQL database. The historical `CHATBOT_DB_PASSWORD` and `CHATBOT_PORT` entries may remain, but Compose no longer uses those names.

Compose passes these files as runtime environment variables. The backend reads `.env` followed by `.docker.env`; the database receives only `.docker.env`. Credentials are not copied into images or exposed to the frontend. The old `.env` bind mount was removed because a non-root container cannot read the host's mode-0600 file. Keep both host files private rather than making them world-readable:

```bash
chmod 600 .env .docker.env
```

`compose.yaml` explicitly sets `DATABASE_URL` to an empty string in the backend, so a stale host URL in `.env` cannot override working Docker credentials. The backend builds the connection from `POSTGRES_USER=chatbot`, `POSTGRES_DB=chatbot`, `DATABASE_HOST=db`, `DATABASE_PORT=5432`, and the password in `.docker.env`. Host development can still use its own `DATABASE_URL` outside Docker; it must point to an accessible database with matching credentials. The existing root `.env` has been preserved rather than rewritten.

Compose env files support quoting. Single-quote values with literal `$` characters and take care with backslashes/quotes. Never print resolved `docker compose config` output, container environment inspection output, `.env` contents or database dumps in shared logs. Docker administrators can inspect runtime secrets; this is a local demo, not a hardened production deployment.

For a new, separate installation only, copy `.env.example` to `.env`, create a private `.docker.env` containing `POSTGRES_PASSWORD` with a long random password, and create the expected volume with `docker volume create chatbot_postgres_data` before startup. Never overwrite this machine's existing files or create a replacement volume as a troubleshooting shortcut. `POSTGRES_*` initializes credentials only when a volume is empty; changing environment values does not change an existing database's password.

## Database preservation and backups

Do not change the database image to PostgreSQL 16: this machine's data directory was initialized by PostgreSQL 17. A major-version upgrade/downgrade needs an explicit database migration, not an image-tag change. Never run two PostgreSQL servers against the same volume, and never remove the volume to resolve credentials or startup problems.

The Compose volume declaration is:

```yaml
volumes:
  postgres_data:
    external: true
    name: chatbot_postgres_data
```

Before the three-service deployment, a custom-format database dump and copies of the previous Compose/private configuration were saved under `/home/minh/leminh/chatbot-backups/20261020-041952/`, with directory mode 0700 and file mode 0600. These backups contain private information and are outside the repository. Existing user/message row counts were preserved during startup. No model request was made for deployment validation.

Create a new private backup when needed:

```bash
backup="$HOME/leminh/chatbot-backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
chmod 700 "$backup"
(umask 077; docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup/database.dump")
```

Backups can contain chat history; do not commit or share them. Restoring is a separate explicit operation and can overwrite data. Stop and investigate failed migrations rather than deleting tables or volumes.

SQLAlchemy maps the existing `chat_users`, `chat_conversations` and `chat_messages` tables. It creates missing tables/indexes and retains the idempotent legacy message-to-conversation upgrade. Each repository operation uses a transaction-scoped session; question/answer insertion is atomic and failures roll back. Connections use pooling and liveness checks, and the engine is disposed on shutdown. There is no Alembic integration yet: changing model columns does not automatically migrate existing tables.

## Routine commands

```bash
docker compose logs --tail 50 -f app
docker compose stop
docker compose up -d --wait
docker compose down
```

Plain `down` retains the external database volume. Avoid `--volumes` in normal shutdown commands and never manually remove `chatbot_postgres_data`. Rebuild after source/dependency changes with `docker compose up -d --build --wait`. After changing runtime settings, use `docker compose up -d --force-recreate --wait`. Recreating the backend clears browser sessions and guest data, not saved PostgreSQL conversations or account files.

## Model and optional services

Set `OPENAI_API_KEY` and optionally `CHAT_MODEL` (default `openai:gpt-4o-mini`) and `OPENAI_BASE_URL` in `.env`. Use an HTTPS OpenAI-compatible gateway if needed; its model ID is passed unchanged. A working provider is needed for chat responses, not for loading the UI. An image-capable model is required for image analysis. Inside containers, `localhost` refers to that container, not the Docker host. This deployment does not change existing provider credentials.

Optional search requires `TAVILY_API_KEY`. The agent decides when to search; the tool sends only the current question, up to 500 characters, not uploaded file content. Without the key, search is unavailable. Search can incur charges; returned evidence links are stored with chat history.

Optional file parsing requires `LLAMA_CLOUD_API_KEY`. `LLAMA_PARSE_TIER` selects `fast`, `cost_effective` (default), `agentic` or `agentic_plus`; unknown values use the default. With the key set, every upload, including guest uploads, is sent to LlamaParse and billed per page; without it, uploads use the local readers. Read [file behavior](files.md) for fallback rules.

Optional tracing requires `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL`. Keep `LANGFUSE_TRACE_CONTENT=false` to redact question, answer and file/prompt content from exported observations. Setting it to true permits content export; do not enable that without authorization. The model provider still receives the readable text/image context required to answer. Traces are flushed at shutdown.

Email/password authentication now replaces the public user selector. Create an account at `/chat` with a display name, email and a password of 12–128 characters; log in with that email/password afterward. Passwords are Argon2id hashes in the new `chat_accounts` table. Display names can repeat; emails are lowercased and unique. Registration always creates a new internal profile: existing `chat_users` records/history are preserved but cannot be claimed by matching a name or email. Legacy-history transfer would require an explicit operator migration with verified ownership, which is not implemented.

`/api/auth/me`, `/register`, `/login`, and `/logout` provide the account flow. Successful authentication rotates the unpredictable session token, clears the previous session's files, and sets an HttpOnly, SameSite=Strict cookie. Session state lives in memory, expires after 12 hours idle or restart, and logout revokes it. Accounts/history remain in PostgreSQL. Login/registration are limited to ten attempts per five-minute window per backend client address; this is process-local and conservative behind the local Next.js proxy. Unsafe requests reject cross-site fetch metadata and mismatched Origin headers; the proxy overwrites the forwarded host for same-origin checks. Chat/file/conversation APIs require either an account or an explicitly started guest session; account history remains unavailable to guests, the compatibility users list shows only the current account, user creation through the old API is forbidden, and another user's profile cannot be selected.

There is no email verification, forgotten-password recovery, OAuth, admin dashboard or persistent login session storage yet. Keep the frontend loopback-only and use a unique password. HTTP cookies are appropriate only on this trusted loopback demo; public deployment would need HTTPS/Secure-cookie enforcement, trusted-proxy configuration, durable sessions and stronger operational controls. Login is not permission to expose the app publicly. Account uploads, revisions and generated downloads are stored in PostgreSQL with their conversation and reload after logout, expiry or restart; guest files stay in memory with the guest tab. Read [file behavior](files.md) for supported input/output formats and limits.

## Guest sessions

Choose **Continue as guest** at `/chat` to chat and use files without an account. `POST /api/auth/guest` returns `guest: true` and a new guest bearer token. The frontend keeps this token in that tab's sessionStorage and passes it as `x-guest-session`; it is not shared through browser cookies. `/api/auth/me` reports that tab's guest status when called with its token. Guest profiles, conversations, messages and citations are not written to PostgreSQL. Every temporary chat in the tab is retained in server RAM, each with its visible history and files. The last 12 messages are used as model context.

There is no guest idle timeout: leaving the tab open, even inactive for hours, preserves its history. Refresh keeps the tab token. Closing an ordinary tab discards its sessionStorage, so opening a new tab starts fresh. A pagehide keepalive request schedules best-effort server cleanup after a 15-second reload grace; a request from a refreshing tab cancels it. This is not a 15-second idle timeout. Backend restart, explicit ending or loss of the tab token also ends guest access. Browser crashes, blocked close requests, tab duplication, session restore and back-forward cache have platform-dependent behavior, so immediate deletion on close cannot be guaranteed; orphaned data may remain in RAM until cleanup/restart and consume session capacity. Browser storage contains only the guest access token and visual preference, not the transcript. If sessionStorage is blocked, the token lasts only in page memory and refresh starts fresh.

**+ New conversation** starts another temporary chat and keeps the previous ones in the sidebar, each with its own transcript and files, until the tab closes. Like account conversations, each guest chat is named automatically from its first message and answer, and can be renamed or deleted but not pinned. **End guest session / Log in** clears the guest session before showing account entry. Signing in or registering does not import or save the guest transcript, and logged-in accounts cannot switch to guest mode without logging out first. Saved PostgreSQL conversations and pinning remain account features. Guest sessions cannot select accounts or read other sessions' files.

The app bypasses its Langfuse trace wrapper and callbacks for guest turns, even if account tracing is configured. The AI provider still receives message/history/file context to answer, and optional web search still sends the current question when used; their retention policies remain external. This is session-only application storage, not a promise that no external provider processes or retains data. Guest model requests still incur the operator's provider costs; keep this app loopback-only.

Tests explicitly forbid guest repository access, check isolated files/transcripts, expiry, restart behavior, cleared transitions, model-failure behavior and trace bypass; browser tests cover guest refresh/reset/end on desktop and mobile.

## Docker validation

Run the offline backend suite using the built image and a read-only test mount:

```bash
docker compose run --rm --no-deps --env LLAMA_CLOUD_API_KEY= --volume "$PWD/tests:/app/tests:ro" app python -m unittest discover -s tests
```

The suite reports 151 tests, including nine PostgreSQL-only integration tests skipped unless `TEST_DATABASE_URL` is set. Authentication and session tests cover hashing, generic invalid-login errors, registration validation, duplicate email, session rotation/revocation, centralized state disposal and timer cancellation, anonymous rejection, cross-account isolation, origin checks, rate limiting and legacy-profile protection. Offline repository tests run real ORM operations in SQLite; API tests mock persistence. Tests are not copied into production images.

Smoke-check the running frontend, proxy and backend:

```bash
curl --fail --silent --output /dev/null http://127.0.0.1:18080/
curl --fail --silent --output /dev/null http://127.0.0.1:18080/chat
curl --fail --silent --output /dev/null http://127.0.0.1:18080/api/auth/me
docker compose exec -T app python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200; assert urllib.request.urlopen('http://127.0.0.1:8000/docs').status == 200"
```

The updated deployment passed these checks with all three services healthy and the original PostgreSQL 17 volume retained. No production conversation write, upload or model request is required for these smoke checks.

### Live browser validation

With the regular Compose stack running, run:

```bash
npm --prefix frontend run test:live
```

This checks the actual deployment at `http://127.0.0.1:18080`, rather than the synthetic E2E backend. Desktop/light and mobile/dark browsers open the landing page, enter a fresh guest workspace and refresh it. The check rejects external network dependencies, HTTP failures and JavaScript errors; screenshots are saved as `frontend/test-results/live-*.png`. Guest sessions are ended afterward. It does not call the model, create accounts or write PostgreSQL history. `CHATBOT_URL` can override the address, but only a loopback origin is accepted.

A successful server-side browser check does not prove that a remote user's browser can reach the server. Use the current VS Code forwarded address or the optional manual tunnel above, not both. Do not publish the unauthenticated local demo to a public interface to work around forwarding problems. If the client still shows white, capture its exact URL, Console errors and failed Network requests; do not assume a server-side HTTP 200 resolves a client rendering failure.

### Isolated fresh-install validation

`tests/compose.yaml` replaces runtime env files with `.env.example`, disables published ports, and replaces the external database volume with a disposable project-owned volume. It requires Compose 2.24.4 or newer. Use a separate project name and both files:

```bash
docker compose --env-file .env.example -p chatbot-setup-test -f compose.yaml -f tests/compose.yaml up -d --build --wait
docker compose --env-file .env.example -p chatbot-setup-test -f compose.yaml -f tests/compose.yaml exec -T app python -c "from app.db import repository; assert repository.users() == []; print('Fresh database ready')"
docker compose --env-file .env.example -p chatbot-setup-test -f compose.yaml -f tests/compose.yaml down --volumes
```

Only this explicitly isolated stack uses a disposable volume. Never copy its `--volumes` cleanup into the normal deployment. The example credentials are for an isolated unpublished test database, not regular deployment.

### PostgreSQL ORM integration tests

Set `TEST_DATABASE_URL` to a dedicated disposable PostgreSQL database, not the application's real database, and run `uv run python -m unittest tests.test_repository -v`. Each PostgreSQL test uses a randomly named schema and drops only that schema at cleanup; the test role needs schema CREATE privileges. These checks cover JSONB sources, uniqueness, conversation ownership, order/limits, cascades, atomic rollback, repeated initialization and legacy history migration. The complete 97-test suite, including account persistence and real authentication/session/history/isolation API checks, passed against an isolated PostgreSQL 17 container. Production uses the original PostgreSQL 17 volume.

## Frontend development

The homepage is `frontend/public/landing.html`, a standalone HTML document with inline CSS/vanilla JS and local Inter fonts in `frontend/public/fonts/` (license included). It makes no external CDN or font requests, so a slow or blocked external service cannot stall parsing and leave a white screen. Open the file directly for a no-build preview; `/chat` links need the application server. Use http://127.0.0.1:18080/ to start from the landing page; when connecting through SSH, forward port 18080 to the browser's computer. Next.js rewrites `/` to this file. The old `frontend/app/page.tsx` and `frontend/app/landing.css` were removed. The Docker build allowlists `public/`, and Docker/start/test runners copy it into the standalone runtime.

Landing and workspace light/dark modes share the `aster-theme` localStorage key. A pre-paint script in each document follows the OS unless a saved choice exists. Workspace Inter is bundled locally via `@fontsource/inter`; landing Inter uses local WOFF2 copies from the same package with `font-display: swap`. The workspace in `frontend/app/` and `frontend/components/` uses a frosted-glass sidebar, header and composer (translucent gradients, a top highlight and backdrop blur over soft colour blobs), a lavender canvas and dark-violet AI bubbles. On desktop the sidebar button collapses the sidebar so the chat uses the full width; the header button reopens it, and the choice is remembered per browser in the `aster-sidebar` localStorage key. On mobile the same buttons open and close the drawer. The Aster logo is an orbit mark: a gradient planet inside a tilted ring with a pink moon (`frontend/components/logo.tsx` in the workspace, the `#aster` symbol and hero mark in `landing.html`, and `public/logo.svg` as the browser icon). Its colours come from the `--logo-*` and `--planet-*` tokens, so it follows the light/dark theme. On the landing page the hero mark's planet appears, the ring draws in and the moon fades in once on load, beside the floating decorative ball, and a light sheen follows the pointer across the hero preview. In the workspace the same intro plays in an empty chat and on the login card, the moon circles the planet in the AI avatar while it is thinking, and new messages ease in. `prefers-reduced-motion` turns all of it off (the ring is shown fully drawn and the moon stays still). The dark theme uses a lifted violet palette (background `#1f1934`, surfaces `#28203f`, AI bubbles `#3a2f63`) on both the landing page and the workspace. `components/auth.tsx` owns login/registration UI; `components/people.tsx` was removed. Theme, uploads, downloads and conversation management remain available after authentication. The Next.js `/api/*` route streams cookies, uploads and downloads to the internal backend without exposing provider secrets to browser code.

With Node.js 24, run:

```bash
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

The frontend suite includes six proxy/source-link tests and 21 browser tests. Browser tests use an isolated synthetic backend on 8101 and frontend on 3100; they do not use real model keys or chat history. Ensure these test-only ports are free before running. Landing checks cover 320, 360, 390, 768 and 1440 pixels in both themes, saved preference, blocked localStorage, absence of external network dependencies, mobile navigation, FAQ links, skip links and reduced motion. Screenshots live in ignored `frontend/test-results/`.

`npm --prefix frontend run dev` serves the development frontend at loopback port 3000 and defaults to backend `http://127.0.0.1:8001`. Local backend development requires a separately accessible test PostgreSQL instance; production Docker PostgreSQL intentionally has no host port. Python dependencies are managed through `pyproject.toml` and `uv.lock`; `uv sync --locked` recreates the optional `.venv` with Python 3.14. Validate locally with `uv run python -m unittest discover -s tests` and smoke-check `app.main:app` with FastAPI's TestClient. Docker remains the recommended workflow here.

Build directories, virtual environments, caches and test reports are disposable and ignored. Keep manifests/lockfiles, source/tests/docs, `.env`, `.docker.env`, `.git/` and `.agents/`. Never delete PostgreSQL volumes or private reports/documents as workspace cleanup.
