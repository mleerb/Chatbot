# AGENTslop

Local FastAPI chatbot with Deep Agents, PostgreSQL-backed users and chat history, browser-session uploads, downloadable generated documents, and optional Tavily web evidence.

## Run on Windows

```powershell
& ".venv-win\Scripts\Activate.ps1"
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Before starting, create a local PostgreSQL database and set `DATABASE_URL` in `.env` as described in [setup](docs/setup.md). Open http://127.0.0.1:8000. The browser code is written in TypeScript (`frontend/chat.ts`); run `npm ci` and `npm run build` when changing it. Node.js is not required just to run the server. Do not expose this unauthenticated demo publicly.

## Read only what you need

- [Setup and validation](docs/setup.md): PostgreSQL, model/Tavily configuration, tests, smoke check.
- [File behavior](docs/files.md): uploads, downloads, generation, and practical limits.
- [Architecture](docs/architecture.md): module map, prompts, sessions, and tracing.
