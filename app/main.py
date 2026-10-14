from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers.generated import router as files_router
from app.routers import chat, documents, users
from app import database
from app.trace import flush_traces

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.initialize()
    yield
    flush_traces()


app = FastAPI(title="AGENTslop", lifespan=lifespan)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(users.router)
app.include_router(files_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")
