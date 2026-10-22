# Safety and validation

- Never print, copy into source files, or commit secrets from `.env` or user documents in `documents/`.
- Keep FastAPI using Deep Agents (`create_deep_agent`), uploaded document context, and optional Langfuse tracing. No terminal interface is required.
- Keep browser uploads in memory and sessions isolated; do not expose this unauthenticated local demo on a public interface.
- Prefer Docker validation: rebuild with `docker compose up -d --build`, run `python -m unittest discover -s tests` in a temporary app container with `tests/` mounted read-only, and smoke-check the running web app. See `docs/setup.md` for exact commands. Host Python environments are optional and are not kept in the cleaned workspace.
