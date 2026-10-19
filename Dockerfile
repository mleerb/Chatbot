FROM ghcr.io/astral-sh/uv:0.13.1 AS uv

FROM python:3.14-slim-bookworm

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

RUN groupadd --system chatbot && useradd --system --gid chatbot --create-home chatbot
COPY --chown=chatbot:chatbot app ./app

USER chatbot
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
