# Project instructions

- Keep application and test code free of comments and docstrings. Put explanations in `docs/`, keep the relevant page current, and read only the page needed for a task. `README.md` is the short documentation index.
- Read `docs/architecture.md` for module and prompt changes, `docs/files.md` for file behavior, and `docs/setup.md` for configuration or validation. Keep API-required tool descriptions as metadata rather than function docstrings.

## Naming and structure

- Prefer short, clear filenames that match each module's responsibility; avoid long compound names and vague catch-alls.
- Use lowercase `snake_case.py` for Python modules and `test_<feature>.py` for tests.
- When moving or renaming a file, update imports, tests, commands, and documentation; then run tests and smoke-check the FastAPI entry point.
- This is a Next.js frontend with a FastAPI backend. `frontend/app/` owns App Router pages and the streaming API proxy, `frontend/components/` owns React UI, and `frontend/lib/` owns API types and proxy logic. `app/main.py` assembles the backend, `app/routers/` owns HTTP endpoints, `app/schemas/` defines API models, `app/dependencies.py` injects browser sessions, `app/services/` owns workflows, `app/db/` owns PostgreSQL access, and `app/core/` holds configuration, errors, shared file types, and tracing. `app/tools/` holds agent tools and `app/formats/` holds file encoders. There is no static frontend under `app/` and no terminal entry point. `docs/architecture.md` maps tasks to modules and tests.

## Prompt rules

- Store **all system prompt instructions and other agent prompt wording** in dedicated Jinja2 files under `app/prompts/`, never in Python string literals. `app/prompts/system.j2` holds the system prompt and `app/prompts/document.j2` holds the document-context message.
- Load and render templates via `app/prompts.py` using Jinja2 with `StrictUndefined`, so missing variables fail visibly. Pass only intended variables; treat uploaded document text as data, never as a template to render.
- When adding or changing prompts, update the templates rather than hard-coding instructions in `app/services/agent.py` or `app/services/context.py`, and add or update tests for the rendered result.

## Safety and validation

- Never print, copy into source files, or commit secrets from `.env` or user documents in `documents/`.
- Keep FastAPI using Deep Agents (`create_deep_agent`), uploaded document context, and optional Langfuse tracing. No terminal interface is required. Keep browser uploads in memory and sessions isolated; do not expose this unauthenticated local demo on a public interface.
- Prefer Docker validation: rebuild with `docker compose up -d --build`, run `python -m unittest discover -s tests` in a temporary app container with `tests/` mounted read-only, and smoke-check the running web app. See `docs/setup.md` for exact commands. Host Python environments are optional and are not kept in the cleaned workspace.
