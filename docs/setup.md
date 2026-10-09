# Setup and validation

On Windows PowerShell, activate `.venv-win/Scripts/Activate.ps1`, install `requirements.txt`, and start `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Open http://127.0.0.1:8000 (`/docs` for API docs); Ctrl+C stops the server.

The root `.env` is loaded at startup and must not be shared or committed. Set `OPENAI_API_KEY` and optionally `CHAT_MODEL` (default `openai:gpt-4o-mini`) and `OPENAI_BASE_URL` for an HTTPS OpenAI-compatible gateway. With a gateway, the model ID is passed unchanged. Existing shell variables override `.env`; restart after changes. A vision-capable model/gateway is required to analyze uploaded images.

Optional Tavily web search requires `TAVILY_API_KEY` in `.env`. Without it, the web-search tool is not offered to the agent. The search tool sends only the current user question (up to 500 characters) to Tavily, never the uploaded file or its filename. Search is invoked by the agent for external/current evidence, not automatically on every turn. Restart after adding the key; Tavily usage may incur charges. The UI shows web-source links only when Tavily actually returns results.

Optional Langfuse tracing requires `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` (EU `https://cloud.langfuse.com`, US `https://us.cloud.langfuse.com`). Input, output, and prompt content are redacted before export by default; `LANGFUSE_TRACE_CONTENT=true` opts into exporting content. With redaction on, Langfuse can show model usage, tool calls and failures but cannot reveal the question or answer for quality debugging. Do not disable redaction unless authorized to export uploaded content. Chat failures mark the root observation as ERROR with a generic status; private exception details stay out of the status. The model provider still receives readable text or image context. Traces are flushed at shutdown.

Validate with `.venv-win/Scripts/python.exe -m unittest discover -s tests`. Smoke-check `app.main:app` with `.venv-win/Scripts/python.exe -c "from app.main import app; from fastapi.testclient import TestClient; assert TestClient(app).get('/').status_code == 200"`.
