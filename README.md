# Document Chat

Local FastAPI chatbot with Deep Agents, browser-session uploads, downloadable generated text and structured documents (Word, PDF, Excel, PowerPoint, ZIP), and optional Tavily web evidence.

## Run on Windows

```powershell

& ".venv-win\Scripts\Activate.ps1"
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Do not expose this unauthenticated demo publicly.

## Read only what you need

- [Setup and validation](docs/setup.md): model/Tavily configuration, tests, smoke check.
- [File behavior](docs/files.md): uploads, downloads, generation, and practical limits.
- [Architecture](docs/architecture.md): module map, prompts, sessions, and tracing.
