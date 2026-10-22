# AGENTS.md

Aster is a local-first AI chat workspace: a Next.js frontend (`frontend/`) proxies to a FastAPI + Deep Agents backend (`app/`) with PostgreSQL 17, all run through Docker Compose on `127.0.0.1:18080`.

## Commands

```bash
docker compose up -d --build --wait
docker compose ps
docker compose logs --tail 50 -f app
docker compose run --rm --no-deps --env LLAMA_CLOUD_API_KEY= --volume "$PWD/tests:/app/tests:ro" app python -m unittest discover -s tests
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

- `code-style.md`: no comments or docstrings, naming and module ownership.
- `prompts.md`: prompt wording lives in Jinja2 templates under `app/prompts/`.
- `safety.md`: secrets, sessions, loopback-only and Docker validation.
- `git.md`: verify the `mleerb` push account and the commit author.
- `reports.md`: daily HTML reports in `reports/`.
- `docs.md`: every change also updates README, `docs/`, `.env.example`, rules and the private guides.

## Docs

- `docs/architecture.md`: module map and prompts.
- `docs/files.md`: file formats and behavior.
- `docs/setup.md`: configuration, backups and validation.
- Shared skills: `.agents/skills/`.
