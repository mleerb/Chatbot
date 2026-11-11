# AGENTS.md

Aster is a local-first AI chat workspace: a Next.js frontend (`frontend/`) proxies to a FastAPI + Deep Agents backend (`app/`) with PostgreSQL 17, all run through Docker Compose on `127.0.0.1:18080`.

## Commands

```bash
docker compose up -d --build --wait
docker compose ps
docker compose logs --tail 50 -f app
docker compose run --rm --no-deps --env LLAMA_CLOUD_API_KEY= --env EMBEDDING_MODEL= --env WORKSPACE_EXPORT_ENABLED=false --volume "$PWD/scripts:/app/scripts:ro" --volume "$PWD/tests:/app/tests:ro" app python -m unittest discover -s tests
npm --prefix frontend run typecheck
npm --prefix frontend run build
npm --prefix frontend test
npm --prefix frontend run test:e2e
npm --prefix frontend run test:live
curl --fail --silent --output /dev/null http://127.0.0.1:18080/
```

Run the backend tests and a smoke check before finishing a change. Never add `--volumes` to `docker compose down`.

## Rules

Detailed rules live in `.claude/rules/`. Claude Code loads them automatically; other agents should read the matching file before a task.

- `planning.md`: show a plan and wait for approval before changing anything.
- `code-style.md`: no comments or docstrings, naming and module ownership.
- `prompts.md`: prompt wording lives in Jinja2 templates under `app/prompts/`.
- `safety.md`: secrets, sessions, loopback-only, chat-only Langfuse tracing (no healthcheck/polling spans) and Docker validation.
- `git.md`: verify the `mleerb` push account and the commit author.
- `reports.md`: daily HTML reports in `reports/`.
- `docs.md`: every change also updates README, `docs/`, `.env.example`, rules and the private guides.

## Docs

- `docs/architecture.md`: module map and prompts.
- `docs/files.md`: file formats, generated previews, revision-bound citations, plain-text source viewing and opt-in private account/guest upload inspection snapshots. This machine's ignored `compose.override.yaml` keeps both exports enabled for ordinary Compose commands.
- `docs/setup.md`: configuration, backups and validation.
- `docs/storage.md`: host-side `python3 scripts/storage.py` report/backup/verify/cleanup commands. Cleanup is explicit-ID, dry-run by default with typed confirmation for deletion; never delete existing snapshots without explicit approval. Restore verification uses isolated tmpfs PostgreSQL, never production. Mount `scripts/` read-only for backend operator-test discovery.
- `docs/acceptance.md`: final regression and live Langfuse message/file/tool redaction plus health-window evidence. `AUDIT_LIVE_TRACING=1 python3 tests/audit_tracing.py` explicitly exports synthetic observations; no paid model calls or production writes. Keep live content settings unchanged without separate approval and distinguish isolated redaction success from enabled live content capture. Embeddings run through the gateway as `nano/text-embedding-3-small` since 11/11.
- `docs/completion.md`: approved phase-by-phase completion work, upload admission limits, configurable timeouts and final privacy acceptance requirements. Stop after each phase; do not commit.
- Shared skills: `.agents/skills/`.
