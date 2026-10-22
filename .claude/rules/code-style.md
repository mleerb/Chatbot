# Code style and structure

- Keep application and test code free of comments and docstrings. Put explanations in `docs/`, keep the relevant page current, and read only the page needed for a task. `README.md` is the short documentation index.
- Read `docs/architecture.md` for module and prompt changes, `docs/files.md` for file behavior, and `docs/setup.md` for configuration or validation. Keep API-required tool descriptions as metadata rather than function docstrings.
- Prefer short, clear filenames that match each module's responsibility; avoid long compound names and vague catch-alls.
- Use lowercase `snake_case.py` for Python modules and `test_<feature>.py` for tests.
- When moving or renaming a file, update imports, tests, commands, and documentation; then run tests and smoke-check the FastAPI entry point.

## Module ownership

- `frontend/app/` owns App Router pages and the streaming API proxy, `frontend/components/` owns React UI, and `frontend/lib/` owns API types and proxy logic.
- `app/main.py` assembles the backend, `app/routers/` owns HTTP endpoints, `app/schemas/` defines API models, `app/dependencies.py` injects browser sessions, `app/services/` owns workflows, `app/db/` owns PostgreSQL access, and `app/core/` holds configuration, errors, shared file types, and tracing.
- `app/tools/` holds agent tools and `app/formats/` holds file encoders.
- There is no static frontend under `app/` and no terminal entry point. `docs/architecture.md` maps tasks to modules and tests.
