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

Use the host-side operator tool for repeatable private backups and isolated recovery validation:

```bash
python3 scripts/storage.py report
python3 scripts/storage.py backup --include-config
python3 scripts/storage.py verify backups/REPLACE_WITH_BACKUP_DIRECTORY
```

See [storage and recovery](storage.md) for permissions, archive contents, resource limits, per-table fingerprint verification, cleanup dry-run/confirmation and manual staging guidance. Backups include private messages/uploads and account password hashes; `--include-config` additionally includes provider/database credentials. Keep them private, Git-ignored and encrypted off-host where appropriate. Verification uses a separate tmpfs-only PostgreSQL 17 container without network or production mounts and never overwrites production. Database and workspace backups are not one atomic snapshot; pause writes first. Actual production restoration remains a separately approved maintenance operation. Stop and investigate failed migrations rather than deleting tables or volumes.

SQLAlchemy maps the existing `chat_users`, `chat_conversations` and `chat_messages` tables. It creates missing tables/indexes, retains the idempotent legacy message-to-conversation upgrade and adds newer columns to existing tables on startup (`chat_messages.attachments`, `stopped`, `rating` and `trace_id`; `chat_usage.uploads` and `images`; nullable `chat_files.embeddings` BYTEA). Each repository operation uses a transaction-scoped session; question/answer insertion is atomic and failures roll back. Connections use pooling and liveness checks, and the engine is disposed on shutdown. There is no Alembic integration yet: changing model columns does not automatically migrate existing tables.

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

Hybrid file retrieval uses `EMBEDDING_MODEL=text-embedding-3-small` by default (512 dimensions), the existing `OPENAI_API_KEY` and HTTPS `OPENAI_BASE_URL` when configured. Set `EMBEDDING_MODEL=` to disable all embedding requests. The provider must support `/embeddings`, the chosen model, token-array inputs and the `dimensions` parameter; advertising chat models alone is not sufficient. The Docker image bundles the `cl100k_base` tokenizer data during build so embedding requests do not need to download tokenizer assets at runtime. Large-file page text is sent at upload, after edits and during first-search backfill of old uploads; queries are also embedded. Account vectors persist in the new nullable `chat_files.embeddings` column and guest vectors stay in RAM. No pgvector extension, database-image change or volume replacement is needed. Embedding tokens are billed by the provider separately and do not count toward daily chat budgets. Failure leaves uploads usable and search explicitly falls back to keywords. Local similarity calculation is not the same as end-to-end latency: new queries need a provider call, and a first-search backfill can be slow. See [file behavior](files.md) for batching, revision reuse and cache details.

Deployment compatibility check on 26/10: the currently configured gateway rejected `text-embedding-3-small` embedding requests with HTTP 400 and advertised no embedding models. Semantic retrieval cannot be considered live-verified on this configuration; use a supported model/gateway before expecting multilingual matches. No credentials or provider URL were changed, and there is no silent direct-OpenAI bypass.

On 09/11 embeddings were switched off with a blank `EMBEDDING_MODEL=` line in the ignored `.env`. On 11/11 embeddings were switched on with `EMBEDDING_MODEL=nano/text-embedding-3-small`: the gateway serves embedding models only under its `nano/` prefix (the plain `text-embedding-3-small` name returns HTTP 400 and its model list shows no names containing "embed"). A one-token 512-dimension probe succeeded, a large guest upload stored embeddings, and synthetic searches such as "how do I fix a flat tyre" ranked the bicycle-repair page first by meaning alone. Chat and embeddings still share `OPENAI_API_KEY`/`OPENAI_BASE_URL`; no separate provider or bypass was added. Changing the model requires `docker compose up -d --wait app`, which logs everyone out. Deleting the line returns to the unprefixed default, which this gateway rejects; a blank `EMBEDDING_MODEL=` switches embeddings off again and search reports `Keyword-only fallback: embeddings disabled or provider key missing.` Existing large uploads are embedded on their first search (backfill).

Optional tracing requires `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL`. Keep `LANGFUSE_TRACE_CONTENT=false` to redact question, answer and file/prompt content from exported observations. Setting it to true permits content export; do not enable that without authorization. The model provider still receives the readable text/image context required to answer. Traces are flushed at shutdown. New traces name each model generation `generate-response` while retaining its model, usage and timing fields. Successful `PatchToolCallsMiddleware.before_agent` and `_ParentNotifierMiddleware.after_agent` observations are filtered from export; failures remain visible. Structural `LangGraph`/`model` wrappers, actual tool calls and real subagents remain to preserve nesting. Existing traces are unchanged. The backend pins the Langfuse 5.2.0 Python SDK (11/11 upgrade from 4.17.0 for the Langfuse v4 platform, which Langfuse Cloud switches to on 16/11/2026). Since v5, observation metadata values are JSON-encoded (a `model` of `gpt-4o-mini` is stored as the JSON string `"gpt-4o-mini"`); masking matches attribute names only, so it is unaffected. Every chat observation carries the propagated session ID, tags and `trace_name=chat-response`, so v4 observation views can filter children by trace name and session cost includes the model generations. The app uses no deprecated public APIs; the acceptance audit reads the v2 observations API through the pinned CLI. v5 logs a harmless `Propagated attribute 'metadata.lc_agent_name' is None` warning per traced turn. Automatic FastAPI HTTP tracing and operation spans are disabled; healthchecks, state polling, authentication, static/file routes and other non-chat requests do not generate Langfuse observations. The export filter additionally accepts only typed `langfuse-sdk` observations, rejecting infrastructure scopes. `LANGFUSE_EXCLUDED_ROUTES` is a comma-separated list of case-sensitive ASGI path globs, default `/*`, excluding all automatic FastAPI request telemetry (including metrics/log telemetry) before processing. For example, `/health,/api/state,/static/*` selects particular paths; an empty value removes path exclusions but does not enable HTTP/operation tracing. Explicit chat answer spans, model/tool callbacks and feedback scores remain enabled independently of these patterns, even with `/*`. Each `chat-response` trace is tagged `document-chat` plus `account` or `guest`, and its Langfuse session ID is the random non-secret `s-…` ID of the browser session (renewed at login, logout and each new guest session, and also recorded in upload `split.md`); the login cookie and guest token are never sent. Traces created before 11/11 used the login cookie as their session ID; those sessions have since ended because the backend restarted. `LANGFUSE_TRACE_GUESTS=true` (default false) also traces guest turns, including message and answer content when `LANGFUSE_TRACE_CONTENT=true`; this machine enables it in the ignored `compose.override.yaml`. Since 11/11 the guest sidebar no longer has a notice box, so guests are not shown a separate tracing notice (operator decision). Rebuild the backend to apply code changes and recreate it after changing settings. Docker healthcheck commands and intervals remain unchanged. When tracing is on, the Good answer / Bad answer buttons under an account answer also set a NUMERIC `user-feedback` score on that answer's trace (1 good, -1 bad, 0 when the rating is cleared); guest answers traced with `LANGFUSE_TRACE_GUESTS=true` are scored the same way. Answers saved before this feature, stopped turns without a trace and untraced guest answers are rated in the app only.

Tracing cleanup validation on 04/11: the rebuilt backend passed 263 tests (242 passed, 21 optional PostgreSQL cases skipped). In-memory tests cover filtering, error retention, redaction, streaming, tool results, token usage and intact nesting. A synthetic Deep Agents tool-use run was exported to Langfuse and read back through the observations API: two `generate-response` generations retained their model and token fields, `search_documents` retained its tool observation, every parent was present, and the two routine middleware observations were absent. This check used fake model responses and synthetic content, with no provider calls, user documents or account-history writes. The backend was redeployed; all three services were healthy and landing/chat/auth-proxy/internal health/docs smoke checks returned HTTP 200. That initial synthetic run verified the agent tree only; later inspection found FastAPI healthcheck spans were still being exported by the overly broad filter. The request-telemetry suppression and SDK-scope allowlist above address that separate issue. Existing runtime keys and content settings were unchanged.

Healthcheck tracing fix verified live on 04/11: the rebuilt backend passed 268 tests (247 passed, 21 optional PostgreSQL cases skipped). Configured tracing is initialized at startup so the idle check exercises an active exporter, not an uninitialized SDK. During 02:36:45–02:38:45 UTC, four unchanged Docker healthchecks returned HTTP 200 and the Langfuse observations API returned zero new observations/traces. One real signed-in `Hi` request at 02:39:24 UTC then produced exactly one trace, `a3244de9690382f0d00d9fa9ec62970c`, with four observations (answer root, LangGraph wrapper, model wrapper and one generation), correct parent links and usage, no tool calls and no HTTP/FastAPI observations. This was a real provider call using a temporary account; the account and its associated database rows were removed after logout. Existing user data, runtime credentials, content settings, Docker healthchecks and the PostgreSQL volume were unchanged. All services remained healthy and smoke checks passed; no commit was made. Existing noisy Langfuse traces are not deleted by this fix.

Email/password authentication now replaces the public user selector. Create an account at `/chat` with a display name, email and a password of 12–128 characters; log in with that email/password afterward. Passwords are Argon2id hashes in the new `chat_accounts` table. Display names can repeat; emails are lowercased and unique. Registration always creates a new internal profile: existing `chat_users` records/history are preserved but cannot be claimed by matching a name or email. Legacy-history transfer would require an explicit operator migration with verified ownership, which is not implemented.

`/api/auth/me`, `/register`, `/login`, and `/logout` provide the account flow. Successful authentication rotates the unpredictable session token, clears the previous session's files, and sets an HttpOnly, SameSite=Strict cookie. Session state lives in memory, expires after 12 hours idle or restart, and logout revokes it. Accounts/history remain in PostgreSQL. Login/registration are limited to ten attempts per five-minute window per backend client address; this is process-local and conservative behind the local Next.js proxy. Unsafe requests reject cross-site fetch metadata and mismatched Origin headers; the proxy overwrites the forwarded host for same-origin checks. Chat/file/conversation APIs require either an account or an explicitly started guest session; account history remains unavailable to guests, the compatibility users list shows only the current account, user creation through the old API is forbidden, and another user's profile cannot be selected.

There is no email verification, forgotten-password recovery, OAuth, admin dashboard or persistent login session storage yet. Keep the frontend loopback-only and use a unique password. HTTP cookies are appropriate only on this trusted loopback demo; public deployment would need HTTPS/Secure-cookie enforcement, trusted-proxy configuration, durable sessions and stronger operational controls. Login is not permission to expose the app publicly. Account uploads, revisions and generated downloads are stored in PostgreSQL with their conversation and reload after logout, expiry or restart; guest live files stay in memory with the guest tab, except separately opted-in workspace text/chunk snapshots retained on disk. Read [file behavior](files.md) for supported input/output formats and limits.

## Reliability limits and completion phases

See [completion status and settings](completion.md) for the approved phased plan. Phase 1 adds positive-integer `UPLOAD_MAX_MB=20`, `CONVERSATION_MAX_FILES=20`, `CONVERSATION_MAX_UPLOAD_MB=100`; MB means MiB. Limits reject new originals only, never delete existing files. Provider timeout settings and slow-network defaults are listed in `.env.example` and the completion guide. Invalid values fail startup. Rebuild after code changes; recreate after private `.env` changes. Persistent local workspace exports for accounts and guests remain enabled through the ignored override.

Backups contain private messages/uploads and account password hashes. Never commit or publish them; use private storage outside the repository where possible. `backups/`, `.dump`, `.backup`, `.sql` and compressed SQL/dump forms are Git-ignored as defense in depth, not a substitute for checking backup filenames. Phase 3 provides host-side storage reporting, private backups, disposable restore verification and manually selected snapshot cleanup through `scripts/storage.py`; see [storage and recovery](storage.md). Cleanup defaults to dry-run, recommends backup, requires an exact selection-bound confirmation and never runs automatically. Existing snapshots were not deleted during implementation.

## Upload inspection workspace

Upload inspection is off by default (`WORKSPACE_EXPORT_ENABLED=false`). It writes document text to disk independently of PostgreSQL and Langfuse. Only enable it for uploads you are authorized to inspect. Guest exports require `WORKSPACE_EXPORT_GUESTS=true` as well (default false); enabling it retains extracted guest text/chunks on disk after guest sessions end. The guest UI warns that upload inspection copies may persist. No original binaries, image data, embedding vectors or credentials are exported. Debug snapshots survive app-side deletion and must be removed manually when no longer needed. Existing uploads and edits are not backfilled.

On this machine, the private Git-ignored `compose.override.yaml` persistently enables both account and guest exports, bind-mounts `.workspace/`, and runs the backend as host UID/GID 1001:1001. Normal `docker compose up -d --build --wait` automatically loads it, so no extra flags are needed; these local choices do not change fresh-install defaults. Explicit `-f compose.yaml` does not auto-load that override.

For other Linux Docker deployments, pre-create a host-owned private directory, then use the optional Compose file. It runs the backend as your numeric host UID/GID (non-root) so host-created mode-0700 files remain readable to you without granting other users access. It does not change the frontend, database, loopback port or healthcheck:

```bash
install -d -m 700 .workspace
WORKSPACE_UID="$(id -u)" WORKSPACE_GID="$(id -g)" \
  docker compose -f compose.yaml -f compose.workspace.yaml up -d --build --wait app
```

When using the optional overlay instead of a persistent private override, continue using both Compose files and the UID/GID variables while that mode is enabled. Recreating the backend clears temporary sessions/guest data, not saved account files. `compose.workspace.yaml` sets `WORKSPACE_EXPORT_ENABLED=true`, `WORKSPACE_EXPORT_DIR=/app/.workspace` and bind-mounts only `./.workspace`. The mount exposes the exports to your host editor, not to HTTP clients. The code refuses a workspace root or uploads directory with group/other permission bits or a symlink. Custom parent directories should also be private and trusted. For host Python execution, set `WORKSPACE_EXPORT_ENABLED=true` and an absolute private `WORKSPACE_EXPORT_DIR` in your shell or private `.env`; without an explicit directory, it uses `<project>/.workspace`. The example Docker path `/app/.workspace` should be changed for host Python.

After a new account or guest upload, start with `split.md`:

```text
.workspace/uploads/<upload-id>/
  split.md         session ID and how the file was extracted and split, step by step
  manifest.json    session ID, filename, parser, source labels, sizes, hashes and chunk count
  steps.json       extraction → splitting → embedding → persistence → context mode
  extracted.txt    extracted text before splitting
  chunks/
    001.txt        exact first page/section text
    002.txt        exact second page/section text
```

Chunk files contain actual processing output, not model-generated summaries. Source page labels and split parts are in the manifest; local sections are not physical document pages. Embedding results reflect the configured provider and may say unavailable/fallback. Inspect [file behavior](files.md#optional-upload-inspection) for retention and snapshot limitations. To disable the Docker mode temporarily, recreate with only the normal Compose file and default false export settings. On this machine, remove or update the private override as well if you want future ordinary Compose commands to stay disabled:

```bash
docker compose -f compose.yaml up -d --force-recreate --wait app
```

The private `.workspace/` snapshots remain until you remove them. Never commit them or expose the folder publicly. `tests/test_workspace.py` covers actual split contents, Unicode, source-page parts, cache/fallback results, modes, account persistence, separately opted-in guest snapshots without database writes, unsafe paths and nonfatal export failure.

Workspace validation on 04/11: 278 backend tests ran successfully (257 passed, 21 optional PostgreSQL cases skipped). A one-off container using the optional overlay and the host numeric UID/GID exported synthetic text through the real upload workflow with fake persistence: two chunk files exactly matched the stored split text, pre-split text matched the input, and the directory was mode 0700. The synthetic export was removed; no user documents or external providers were accessed. `.workspace/README.md` and an empty uploads directory were left private for orientation. The backend was rebuilt/redeployed in normal mode with export disabled; all services are healthy and frontend/chat/auth/internal health/docs checks returned HTTP 200. No commit was made.

Persistent workspace export validation on 05/11: the operator approved both account and guest upload snapshots. The private ignored `compose.override.yaml` enables `WORKSPACE_EXPORT_ENABLED=true` and `WORKSPACE_EXPORT_GUESTS=true`, binds the host directory and uses UID/GID 1001:1001; normal Compose configuration validates and the deployed container confirms both flags true. All 280 backend tests completed (259 passed, 21 optional PostgreSQL cases skipped), frontend typecheck/production Docker build and all 10 frontend unit tests passed. A synthetic guest text upload through the live frontend proxy created two chunk files, `steps.json`, `manifest.json` and `extracted.txt` on the host with private permissions, recorded in-memory guest persistence, and remained after guest logout. Only that synthetic snapshot was then removed. The live upload used the existing parser configuration; no model chat call or account-history write was needed. Both app images were redeployed, guest-retention notices updated, and services/smoke checks passed. Previous account-only/disabled validation above records the earlier deployment, not current local settings. No commit was made.

## Final acceptance

All four approved completion phases are recorded in [completion status](completion.md); detailed evidence and rerun instructions are in [final acceptance](acceptance.md). Final checks passed 320 backend tests (296 passed/24 skipped), frontend typecheck/build/10 unit tests/39 browser tests, live desktop/mobile smoke checks, actual Langfuse redaction read-back for message/file/tool content in separate redacted workers, and a fresh 120-second zero-observation health window. This does not change live privacy settings: runtime `LANGFUSE_TRACE_CONTENT=true` remains enabled, so ordinary account prompts/file content can still be exported. Changing it requires separate approval and backend recreation. At that time embeddings were unavailable and long-file retrieval used keyword fallback; they were switched on later, on 11/11 (see [hybrid retrieval](#model-and-optional-services) above). Account and guest workspace exports remain persistently enabled. No Phase 4 application rebuild/restart was needed.

## Upload experience

Phase 2 adds File help near the composer, showing configured limits and whether cloud parsing is available. No new environment setting is needed. Rebuild backend and frontend together for `/api/document/settings` and the UI. Settings require an account or guest session and never reveal credentials. Ready/Check file disclosures show actual extraction and retrieval statuses; batches show current processing versus queued files without invented percentages. Individual failed uploads can be retried/dismissed, while successful attachments and draft text remain. Retried requests are not idempotent: check attachments first after an ambiguous network failure to avoid duplicate files. Failed File objects live only in tab memory and clear on conversation/identity change or reload. See [completion status](completion.md).

## Document acceptance audit

See [the audit results and rerun procedure](document-audit.md). On 05/11, eight provider-backed synthetic answer requests passed the sampled fact/citation/honesty checks, including streamed long-PDF retrieval and scanned-PDF OCR. Seven workspace snapshots matched stored chunks; logout/login and cross-conversation source rejection passed. Five test accounts and seven snapshots were cleaned up. The configured embedding model still returned HTTP 400, and retrieval explicitly used keyword fallback; no provider settings were changed. Langfuse showed exactly eight traces, intact nesting and no HTTP/FastAPI noise. All 35 synthetic browser tests passed after installing the missing Playwright Chromium. The explicit-cost opt-in script is `tests/audit_documents.py`; it is not part of ordinary unit-test discovery.

## Citation viewer validation

Document citations need no new settings, credentials or schema migration and do not change embedding configuration. Rebuild both application images to enable the new `/api/sources/{source_id}` endpoint and UI. Existing account message `sources` JSON now retains exact extracted-text snapshots for cited document revisions; allow for larger history/backups. The snapshots are omitted from ordinary response metadata and are served only after conversation ownership and file-presence checks. Removed files return an unavailable-source state; existing saved answers are not retroactively cited.

`tests/test_citations.py` exercises English/Vietnamese inline sections, page reads, HTML/script text, old/new revisions and reload, distinct web/document markers, foreign account/guest IDs, removed/replaced sources, failed turns, streaming and Stop. `tests/test_repository.py` checks real JSON snapshot roundtrip and scoped source access. Frontend unit tests cover marker transformation and unfinished drafts; `frontend/e2e/citations.spec.ts` verifies escaped source text, inert script/image/link content, desktop/mobile layout, refresh, Escape/focus restoration and unavailable-source feedback. These tests use synthetic documents and fake model/search providers, not production uploads or paid embedding requests.

Validation on 27/10: frontend typecheck, production build, 10 unit tests and all 32 synthetic-backend browser tests passed. The first deployment failed during backend image extraction with `no space left on device`. After operator-approved chatbot-only cleanup of unused old/test images, selected old build-cache IDs and regenerable frontend output, the normal `docker compose up -d --build --wait` completed successfully. The rebuilt image passed 250 backend tests (229 passed, 21 optional PostgreSQL cases skipped), with live parsing/embedding requests disabled. All three services are healthy; frontend/proxy/internal smoke checks returned HTTP 200 and the deployed OpenAPI schema includes `/api/sources/{source_id}`. Desktop/mobile live browser checks passed landing → guest workspace → refresh without external requests, HTTP/JavaScript errors, model calls or account/history writes. The existing PostgreSQL 17 volume, secrets and embedding configuration were preserved; approximately 6.3 GiB remained free after deployment. No commit was made.

## Standalone generated-file validation

Standalone text/code/data files need no new configuration. System instructions and the `create_text_file` description list the backend allowlist explicitly and preserve requested extensions; ZIP is used only for an explicitly requested archive. Rebuild the backend after changing these templates. A fresh conversation avoids earlier misleading capability answers in history.

On 27/10, the rebuilt image passed 253 backend tests (232 passed, 21 optional PostgreSQL cases skipped). New tests check all 13 text extensions, separate HTML/Markdown/JSON/CSV/Python downloads, English/Vietnamese UTF-8 bytes, attachment/nosniff headers and account reload. A live synthetic guest streaming request created five individual files (`index.html`, `README.md`, `data.json`, `data.csv`, `example.py`), and a second ordinary-language request without a tool name created `hello.html` and `README.md` separately. Downloads were verified as UTF-8, not ZIP; both temporary guest sessions were ended. These model calls used the existing configured gateway, with no private documents, embedding calls or account-history writes. All services remained healthy and HTTP smoke checks returned 200. This verifies the sampled requests, not every possible model response.

## Generated previews

Generated-file previews require no new keys, environment settings or database migration. The frontend locks `pdfjs-dist` in npm and runs `pdf-assets.mjs` before dev/build to copy its matching worker, fonts, CMaps, WASM assets and license into ignored `public/pdfjs/`; these are served locally, not through a CDN. Docker includes the asset-copy script in its allowlisted build context and generates the files in the build stage. Rebuild both services after this update. No change to embedding configuration is needed.

Backend `tests/test_preview.py` covers English/Vietnamese text, Office/ZIP/PDF extraction, formulas-as-text, malformed/oversized archives, download preservation, account reload, guessed file IDs, account/guest/conversation isolation and stale deleted files. Browser `e2e/preview.spec.ts` covers desktop/mobile HTML rendering with script/resource/navigation payloads blocked, raw source text, a two-page local PDF with page/zoom controls and download, refresh, sheet/slide/archive views and unavailable feedback. Synthetic E2E uses a small committed two-page PDF fixture, not production files or model calls.

Preview validation on 27/10: frontend typecheck, 10 unit tests, production build and all 35 synthetic browser tests passed, including isolated HTML and two-page local PDF at 1440/360px. Deployment initially paused because the shared disk had under 200 MiB free. After the server filesystem was expanded to about 290 GiB, the requested redeployment succeeded; a transient npm ECONNRESET during the first frontend build cleared on retry without configuration changes. The rebuilt image passed 259 backend tests (238 passed, 21 optional PostgreSQL tests skipped), with live parsing/embedding disabled. All services are healthy; frontend/auth/worker/license smoke checks returned HTTP 200, both preview routes appear in deployed OpenAPI, and desktop/mobile live browser checks passed landing → guest → refresh without external requests, HTTP/JavaScript errors, model calls or account/history writes. Approximately 86 GiB remained available at the final disk check (shared-server usage varies). Existing PostgreSQL storage and embedding settings were preserved; no cleanup or commit was made during redeployment.

## Account usage limit

Each account can use `USER_TOKEN_LIMIT` tokens (set in `.env`, default `500000`) per calendar day. Both this limit and the guest budget count day by day and reset at 00:00 in `LIMIT_TIMEZONE` (an IANA time zone name, default `Asia/Ho_Chi_Minh`); the server's clock decides, not the browser's, so changing the computer's time zone does not reset a limit. Usage is counted the same way as the guest budget: the model-reported total tokens of each successful turn, including the system prompt, tool definitions, history and file context (about 3,000 tokens for a short question), so the default allows roughly 150 short turns a day, or fewer with long conversations or large files. Once the limit is reached, `/api/chat` and uploads return 403 with "Daily limit reached. Chat and uploads open again after midnight." until midnight; reading, renaming, pinning and deleting conversations, downloads and exports keep working. `/api/state` and `/api/chat` return `limit_resets_at` (the next midnight as an ISO timestamp while blocked, otherwise `null`), never the usage or the limit; the workspace freezes the composer, shows the reopening time in the browser's local time and unlocks itself when it passes. The limit belongs to the account, so logging in from another browser or device does not reset it. Counts are stored in the PostgreSQL `chat_usage` table and survive restarts. The last turn may go slightly over the limit because usage is only known after the answer; if recording usage fails, the answer is still saved and the failure is logged. Uploads have their own daily count, `UPLOAD_LIMIT` (default `5` files per account or guest browser), with the same midnight reset; see [file behavior](files.md). Change these settings with `docker compose up -d --force-recreate --wait` after editing `.env`.

## Image generation

Image generation is off until `IMAGE_MODEL` is set in `.env`. It uses the same `OPENAI_API_KEY` and, when set, `OPENAI_BASE_URL` as chat, and calls the OpenAI Images API (`images.generate`, PNG output). With a direct OpenAI key, use a current GPT Image model such as `gpt-image-2.5-flare` (fast, everyday) or `gpt-image-2.5-sunburst` (most capable); `gpt-image-1` was shut down on 23 October 2026 and `gpt-image-1.5` and `gpt-image-1-mini` shut down on 1 December 2026, so check OpenAI's deprecations page before choosing. A gateway must offer an image model through its Images endpoint; list its models before enabling the feature, because a model the gateway does not have makes every attempt fail (no image is created or counted). `IMAGE_QUALITY` (default `medium`) and `IMAGE_SIZE` (default `1024x1024`; `1536x1024` and `1024x1536` are also accepted) set the defaults, and the agent may pick landscape or portrait when asked. `IMAGE_LIMIT` (default `10`) and `GUEST_IMAGE_LIMIT` (default `2`) cap images per account and per guest browser a day, with the midnight reset above. Each image is a paid provider call, a few cents at medium quality on recent OpenAI models. Recreate the containers after changing these settings. See [file behavior](files.md) for how images are stored and shown.

## Guest sessions

Choose **Continue as guest** at `/chat` to chat and use files without an account. `POST /api/auth/guest` returns `guest: true` and a new guest bearer token. The frontend keeps this token in that tab's sessionStorage and passes it as `x-guest-session`; it is not shared through browser cookies. `/api/auth/me` reports that tab's guest status when called with its token. Guest profiles, conversations, messages and citations are not written to PostgreSQL. When both `WORKSPACE_EXPORT_ENABLED` and `WORKSPACE_EXPORT_GUESTS` are true, extracted upload text and chunks are copied to private disk snapshots and outlive the guest session until manually removed; this machine enables that operator-approved exception through its ignored Compose override. The tab's single temporary chat is retained in server RAM with its visible history and files. The last 12 messages are used as model context.

There is no guest idle timeout: leaving the tab open, even inactive for hours, preserves its history. Refresh keeps the tab token. Closing an ordinary tab discards its sessionStorage, so opening a new tab starts fresh. A pagehide keepalive request schedules best-effort server cleanup after a 15-second reload grace; a request from a refreshing tab cancels it. This is not a 15-second idle timeout. Backend restart, explicit ending or loss of the tab token also ends guest access. Browser crashes, blocked close requests, tab duplication, session restore and back-forward cache have platform-dependent behavior, so immediate deletion on close cannot be guaranteed; orphaned data may remain in RAM until cleanup/restart and consume session capacity. Browser storage contains only the guest access token and visual preference, not the transcript. If sessionStorage is blocked, the token lasts only in page memory and refresh starts fresh.

**+ New conversation** asks for confirmation, then deletes the current temporary chat and its files and starts a new one; a guest never has more than one chat. Like account conversations, the guest chat is named automatically from its first message and answer, and can be renamed or deleted but not pinned. **End guest session / Log in** clears the guest session before showing account entry. Signing in or registering does not import or save the guest transcript, and logged-in accounts cannot switch to guest mode without logging out first. Saved PostgreSQL conversations and pinning remain account features. Guest sessions cannot select accounts or read other sessions' files.

Each browser has a guest token budget set by `GUEST_TOKEN_LIMIT` in `.env` (default `50000`), shared by all its guest tabs. Usage is the model-reported total tokens of each successful turn, including the system prompt, tool definitions, history and file context, so a short question costs roughly 3,000 tokens with the default agent and 50,000 allows about fifteen short turns; longer history or attached files use it faster. Guests never see the usage or the limit; the API returns only a `guest_limited` flag and the `limit_resets_at` reopening time. The browser is recognised by an HttpOnly `aster_guest` cookie that holds only a random meter ID (30-day lifetime); it is separate from the per-tab guest session token and grants no access to any chat. Starting a new chat, opening a new tab or ending the guest session does not reset the budget. The budget is counted per calendar day and resets at midnight in `LIMIT_TIMEZONE`, like the account limit below; once it is used up, guest chat is blocked in that browser until then. While blocked, `/api/chat` and guest uploads return 403 with "Guest limit reached. Guest chat is available again after midnight; log in or sign up to keep chatting now.", the composer is frozen, and Sign up / Log in buttons end the guest session and open the account form. The last turn may go slightly over the limit because usage is only known after the answer. Counts live in server memory, so restarting the backend clears them; clearing cookies, a private window or another browser also gets a new budget.

By default the app bypasses its Langfuse trace wrapper and callbacks for guest turns, even if account tracing is configured; `LANGFUSE_TRACE_GUESTS=true` traces them like account turns, tagged `guest`. The AI provider still receives message/history/file context to answer, and optional web search still sends the current question when used; their retention policies remain external. This is session-only application storage, not a promise that no external provider processes or retains data. Guest model requests still incur the operator's provider costs; keep this app loopback-only.

Tests explicitly forbid guest repository access, check isolated files/transcripts, expiry, restart behavior, cleared transitions, model-failure behavior, the default trace bypass and opt-in guest tracing; browser tests cover guest refresh/reset/end on desktop and mobile.

## Docker validation

Run the offline backend suite using the built image and a read-only test mount:

```bash
docker compose run --rm --no-deps --env LLAMA_CLOUD_API_KEY= --env EMBEDDING_MODEL= --env WORKSPACE_EXPORT_ENABLED=false --volume "$PWD/scripts:/app/scripts:ro" --volume "$PWD/tests:/app/tests:ro" app python -m unittest discover -s tests
```

The suite includes hybrid ranking, multilingual fake-provider retrieval, multi-file isolation, upload/query failure fallback, bounded batching/cache, edit reuse, old-file backfill, guest database bypass and additive migration tests. Set `EMBEDDING_MODEL=` for offline runs so existing upload tests cannot send document text to a real provider; the new embedding tests inject a fake provider explicitly. The 26/10 offline Docker run completed 234 tests with no failures (214 passed, 20 PostgreSQL-only cases skipped). Set `TEST_DATABASE_URL` only to a disposable test database to enable PostgreSQL cases. Against a separate disposable PostgreSQL 17 instance, 19 PostgreSQL cases passed including the new nullable BYTEA migration/backfill test. The full PostgreSQL-enabled suite also exposed an existing unrelated fixture failure: `test_initialization_adds_upload_count_to_existing_usage` declares SQLite `DATETIME` in PostgreSQL, which rejects that type. This fixture is not changed by hybrid retrieval, so the full PostgreSQL-enabled suite is not reported as green. The app container receives the private `.env`, so tests that run real tracing code (streaming, ratings) clear the Langfuse variables first and never contact Langfuse. Authentication and session tests cover hashing, generic invalid-login errors, registration validation, duplicate email, session rotation/revocation, centralized state disposal and timer cancellation, anonymous rejection, cross-account isolation, origin checks, rate limiting and legacy-profile protection. Offline repository tests run real ORM operations in SQLite; API tests mock persistence. Tests are not copied into production images.

Smoke-check the running frontend, proxy and backend:

```bash
curl --fail --silent --output /dev/null http://127.0.0.1:18080/
curl --fail --silent --output /dev/null http://127.0.0.1:18080/chat
curl --fail --silent --output /dev/null http://127.0.0.1:18080/api/auth/me
docker compose exec -T app python -c "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8000/health').status == 200; assert urllib.request.urlopen('http://127.0.0.1:8000/docs').status == 200"
```

The updated deployment passed these checks with all three services healthy and the original PostgreSQL 17 volume retained. No production conversation write, upload or model request is required for these smoke checks.

To check that answers stream through the proxy, send one short guest question (one model request; guest turns are not saved, and are traced only when `LANGFUSE_TRACE_GUESTS=true`, as on this machine). Text events should arrive one by one before the final `done` event:

```bash
token=$(curl -s -X POST http://127.0.0.1:18080/api/auth/guest | python3 -c "import sys, json; print(json.load(sys.stdin)['guest_token'])")
curl -sN -X POST http://127.0.0.1:18080/api/chat/stream -H "x-guest-session: $token" -H 'content-type: application/json' -d '{"message":"Count to five in words."}'
curl -s -o /dev/null -X POST http://127.0.0.1:18080/api/auth/guest/close -H "x-guest-session: $token"
```

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

Landing and workspace light/dark modes share the `aster-theme` localStorage key. A pre-paint script in each document follows the OS unless a saved choice exists. Workspace Inter is bundled locally via `@fontsource/inter`; landing Inter uses local WOFF2 copies from the same package with `font-display: swap`. The workspace in `frontend/app/` and `frontend/components/` uses a frosted-glass sidebar, header and composer (translucent gradients, a top highlight and backdrop blur over soft colour blobs), a lavender canvas and dark-violet AI bubbles. On desktop the sidebar button collapses the sidebar so the chat uses the full width; the header button reopens it, and the choice is remembered per browser in the `aster-sidebar` localStorage key. On mobile the same buttons open and close the drawer. The Aster logo is an orbit mark: a gradient planet inside a tilted ring with a pink moon (`frontend/components/logo.tsx` in the workspace, the `#aster` symbol and hero mark in `landing.html`, and `public/logo.svg` as the browser icon). Its colours come from the `--logo-*` and `--planet-*` tokens, so it follows the light/dark theme. On the landing page the hero mark's planet appears, the ring draws in and the moon fades in once on load, beside the floating decorative ball, and a light sheen follows the pointer across the hero preview. In the workspace the same intro plays in an empty chat and on the login card, the moon circles the planet in the AI avatar while it is thinking, and new messages ease in. `prefers-reduced-motion` turns all of it off (the ring is shown fully drawn and the moon stays still). The dark theme uses a lifted violet palette (background `#1f1934`, surfaces `#28203f`, AI bubbles `#3a2f63`) on both the landing page and the workspace. `components/auth.tsx` owns login/registration UI; `components/people.tsx` was removed. Theme, uploads, downloads and conversation management remain available after authentication. The Next.js `/api/*` route streams cookies, uploads, downloads and streamed answers to and from the internal backend without exposing provider secrets to browser code.

With Node.js 24, run:

```bash
npm --prefix frontend ci
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

The frontend suite includes proxy/source-link and citation unit tests (including chunk-by-chunk event-stream forwarding), plus browser tests for citation viewing and the existing chat/landing workflows (including streaming with a tool step, Stop, Copy, ratings, Edit and Regenerate in `e2e/controls.spec.ts`). Browser tests use an isolated synthetic backend on 8101 and frontend on 3100; they do not use real model keys or chat history. Ensure these test-only ports are free before running. Landing checks cover 320, 360, 390, 768 and 1440 pixels in both themes, saved preference, blocked localStorage, absence of external network dependencies, mobile navigation, FAQ links, skip links and reduced motion. Screenshots live in ignored `frontend/test-results/`.

`npm --prefix frontend run dev` serves the development frontend at loopback port 3000 and defaults to backend `http://127.0.0.1:8001`. Local backend development requires a separately accessible test PostgreSQL instance; production Docker PostgreSQL intentionally has no host port. Python dependencies are managed through `pyproject.toml` and `uv.lock`; `uv sync --locked` recreates the optional `.venv` with Python 3.14. Validate locally with `uv run python -m unittest discover -s tests` and smoke-check `app.main:app` with FastAPI's TestClient. Docker remains the recommended workflow here.

Build directories, virtual environments, caches and test reports are disposable and ignored. Keep manifests/lockfiles, source/tests/docs, `.env`, `.docker.env`, `.git/` and `.agents/`. Never delete PostgreSQL volumes or private reports/documents as workspace cleanup.
